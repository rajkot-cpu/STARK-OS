# apps/windows-cc/screen.py
"""Screen reading (R3 every capture): mss grab -> downscale JPEG -> vision describe.

The JPEG stays in memory only (never written to disk). Callers must audit.
"""
from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request

MAX_W = 1280
VISION_MODEL = "gemini-3.1-flash-lite-preview"
PROMPT = ("Describe what is on this computer screen for the operator, briefly and factually. "
          "Do not read out passwords, card numbers, Aadhaar/PAN numbers or patient identifiers; "
          "summarize such fields as [redacted].")


def available() -> tuple[bool, str]:
    try:
        import mss  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception as e:
        return False, f"missing dependency: {type(e).__name__}"
    return True, ""


def capture_jpeg(max_w: int = MAX_W, quality: int = 70) -> bytes:
    import mss
    from PIL import Image

    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _gemini_vision(jpeg: bytes, question: str, key: str, timeout: float = 45.0) -> str:
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{VISION_MODEL}:generateContent?key={key}")
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": f"{PROMPT}\nOperator question: {question or 'What is on my screen?'}"},
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}},
        ]}],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.2},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}") from None
    parts = ((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = " ".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("vision returned empty reply")
    return text[:2000]


def _openai_vision(jpeg: bytes, question: str, key: str, timeout: float = 45.0) -> str:
    body = {
        "model": "gpt-4o-mini",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": f"{PROMPT}\nOperator question: {question or 'What is on my screen?'}"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}},
        ]}],
    }
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI HTTP {e.code}") from None
    text = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise RuntimeError("vision returned empty reply")
    return text.strip()[:2000]


def read_screen(question: str = "", *, gemini_key: str = "", openai_key: str = "",
                capture=None, gemini_fn=None, openai_fn=None) -> dict:
    """Capture once and describe. Caller is responsible for R3 confirm + audit."""
    capture = capture or capture_jpeg
    gemini_fn = gemini_fn or _gemini_vision
    openai_fn = openai_fn or _openai_vision
    if not gemini_key and not openai_key:
        return {"ok": False, "error": "No Gemini/OpenAI key for vision"}
    try:
        jpeg = capture()
    except Exception as e:
        return {"ok": False, "error": f"capture failed: {type(e).__name__}: {str(e)[:120]}"}
    errors = []
    try:
        if gemini_key:
            try:
                return {"ok": True, "data": {"description": gemini_fn(jpeg, question, gemini_key),
                                             "provider": "gemini", "bytes": len(jpeg)}}
            except Exception as e:
                errors.append(f"gemini: {str(e)[:80]}")
        if openai_key:
            try:
                return {"ok": True, "data": {"description": openai_fn(jpeg, question, openai_key),
                                             "provider": "openai", "bytes": len(jpeg)}}
            except Exception as e:
                errors.append(f"openai: {str(e)[:80]}")
    finally:
        del jpeg
    return {"ok": False, "error": "; ".join(errors) or "vision failed"}
