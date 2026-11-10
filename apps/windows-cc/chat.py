# apps/windows-cc/chat.py
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from llm_providers import USER_AGENT, groq_extra, groq_model, load_secrets, _resolve_key


SYSTEM = (
    "You are JARVIS, STARK OS voice assistant for Dr Chandan Kumar. "
    "Reply in 1-2 short spoken sentences. Match the user's language (Hindi/English). "
    "Be calm, precise, dryly witty. Never invent tool actions you did not take. "
    "If asked to do something that needs the panel, say you will note it. "
    "You cannot build, create, write or run anything from this chat, and you never claim you did. "
    "If the user asks you to build or make something (an app, game, website, file), tell them to type "
    "or say it as a command, for example 'build me a snake game in html', so the Builder agent starts."
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _gemini_reply(prompt: str, key: str, timeout: float = 45.0) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-3.1-flash-lite-preview:generateContent?key={key}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 120, "temperature": 0.6},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Gemini HTTP {e.code}: {err}") from e
    parts = (
        raw.get("candidates") or [{}]
    )[0].get("content", {}).get("parts") or []
    text = " ".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty reply")
    return text[:400]




def _openai_reply(prompt: str, key: str, timeout: float = 45.0, *,
                  url: str = "https://api.openai.com/v1/chat/completions", model: str = "gpt-4o-mini",
                  extra: dict | None = None) -> str:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 120,
        "temperature": 0.6,
    }
    if extra:
        body.update(extra)
        body["max_tokens"] = 400  # reasoning tokens count against the budget
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                 "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    text = (raw.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    if not text:
        raise RuntimeError("OpenAI returned empty reply")
    return text[:400]


def _groq_reply(prompt: str, key: str, timeout: float = 45.0) -> str:
    """Groq speaks the OpenAI chat.completions dialect."""
    model = groq_model()
    return _openai_reply(prompt, key, timeout, url=GROQ_URL, model=model, extra=groq_extra(model))


def reply(user_text: str, root: Path | None = None) -> dict:
    text = (user_text or "").strip()
    if not text:
        return {"ok": False, "error": "empty utterance"}
    load_secrets(root)
    gkey = _resolve_key("JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    okey = _resolve_key("JARVIS_OPENAI_API_KEY", ("OPENAI_API_KEY",))
    qkey = _resolve_key("JARVIS_GROQ_API_KEY", ("GROQ_API_KEY",))
    errors = []
    if gkey:
        try:
            answer = _gemini_reply(text, gkey)
            return {"ok": True, "data": {"reply": answer, "heard": text, "provider": "gemini"}}
        except Exception as e:
            errors.append(f"gemini: {e}")
    if okey:
        try:
            answer = _openai_reply(text, okey)
            return {"ok": True, "data": {"reply": answer, "heard": text, "provider": "openai"}}
        except Exception as e:
            errors.append(f"openai: {e}")
    if qkey:
        try:
            answer = _groq_reply(text, qkey)
            return {"ok": True, "data": {"reply": answer, "heard": text, "provider": "groq"}}
        except Exception as e:
            errors.append(f"groq: {e}")
    if not gkey and not okey and not qkey:
        return {"ok": False, "error": "No LLM key — add Gemini, OpenAI or Groq in secrets/api_keys.env"}
    return {"ok": False, "error": "; ".join(errors) or "chat failed"}
