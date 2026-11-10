"""Plain-text LLM completions with the same Gemini -> OpenAI -> Groq fallback the agents use."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from llm_providers import USER_AGENT, groq_extra, groq_model

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
OPENAI_MODEL = "gpt-4o-mini"
LABEL = {"gemini": "Gemini", "openai": "OpenAI", "groq": "Groq"}


class LLMFailed(RuntimeError):
    pass


def _post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _one(name, key, system, prompt, max_tokens, json_mode, timeout):
    if name == "gemini":
        cfg = {"maxOutputTokens": max_tokens, "temperature": 0.7}
        if json_mode:
            cfg["responseMimeType"] = "application/json"
        raw = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}",
                    {"systemInstruction": {"parts": [{"text": system}]},
                     "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": cfg},
                    {}, timeout)
        parts = (raw.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if name == "groq":
        url, model = "https://api.groq.com/openai/v1/chat/completions", groq_model()
    else:
        url, model = "https://api.openai.com/v1/chat/completions", OPENAI_MODEL
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.7}
    if name == "groq":
        body.update(groq_extra(model))
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    raw = _post(url, body, {"Authorization": f"Bearer {key}"}, timeout)
    return ((raw.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def complete(providers: list[tuple[str, str]], system: str, prompt: str, *, max_tokens: int = 3000,
             json_mode: bool = False, timeout: float = 90.0, on_note=None, sleep=time.sleep) -> tuple[str, str]:
    """Return (text, provider). providers: [(name, key)] in fallback order. Never logs keys."""
    notes = []
    for name, key in providers:
        for attempt in range(3):
            try:
                text = _one(name, key, system, prompt, max_tokens, json_mode, timeout)
                if text:
                    return text, name
                notes.append(f"{LABEL.get(name, name)} empty reply")
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:500].lower()
                if e.code == 429 and "insufficient_quota" not in body and attempt < 2:
                    if on_note:
                        on_note(f"{LABEL.get(name, name)} busy (429), retrying in {10 * (attempt + 1)}s")
                    sleep(10 * (attempt + 1))
                    continue
                if e.code >= 500 and attempt < 1:
                    sleep(3)
                    continue
                notes.append(f"{LABEL.get(name, name)} HTTP {e.code}")
                break
            except Exception as e:  # noqa: BLE001 — network/timeouts
                notes.append(f"{LABEL.get(name, name)} {type(e).__name__}")
                break
        if on_note and notes:
            on_note("⚠ " + notes[-1])
    raise LLMFailed("All AI providers failed: " + "; ".join(notes))
