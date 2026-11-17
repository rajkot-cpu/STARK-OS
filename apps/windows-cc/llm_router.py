# apps/windows-cc/llm_router.py
"""Hybrid text completion: cloud providers first, local Ollama as fallback / offline (Phase 3).

ai_mode (cc_settings): hybrid (default) | local_first | cloud_only.
cheap=True (classification, short summaries) tries the local model first in hybrid mode,
so routine work costs nothing and still works offline. Never logs prompts or keys.
A provider that answers HTTP 429 (rate limit) is skipped for COOLDOWN_S, so the next provider in the
plan (e.g. Gemini 429 -> OpenAI/Groq -> local Ollama) answers immediately instead.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import local_llm
from llm_providers import USER_AGENT, _resolve_key, groq_extra, groq_model, load_secrets

OPENAI_MODEL = "gpt-4o-mini"
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
CLOUD = (
    ("gemini", "JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    ("openai", "JARVIS_OPENAI_API_KEY", ("OPENAI_API_KEY",)),
    ("groq", "JARVIS_GROQ_API_KEY", ("GROQ_API_KEY",)),
)


COOLDOWN_S = 120.0
_cooldown: dict[str, float] = {}  # provider -> monotonic time until which it is skipped (after HTTP 429)


def cooling(name: str) -> float:
    """Seconds left before a rate-limited provider is tried again (0 = usable)."""
    import time

    return max(0.0, _cooldown.get(name, 0.0) - time.monotonic())


class Halted(RuntimeError):
    pass


def _halted() -> bool:
    try:
        import halt

        h = halt.current()
        return bool(h and h.is_stopped())
    except Exception:
        return False


def settings(root) -> dict:
    try:
        import cc_settings

        s = cc_settings.load(root)
        return {"ai_mode": s.get("ai_mode", "hybrid"), "local_model": s.get("local_model", local_llm.DEFAULT_MODEL)}
    except Exception:
        return {"ai_mode": "hybrid", "local_model": local_llm.DEFAULT_MODEL}


def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"unreachable ({type(e).__name__})") from e


def _gemini(system: str, prompt: str, key: str, max_tokens: int, timeout: float) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    raw = _post(url, {"x-goog-api-key": key}, {
        "systemInstruction": {"parts": [{"text": system or "You are a helpful assistant."}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": int(max_tokens), "temperature": 0.4},
    }, timeout)
    parts = ((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return " ".join(str(p.get("text", "")) for p in parts).strip()


def _openai_compat(system: str, prompt: str, key: str, max_tokens: int, timeout: float, provider: str) -> str:
    if provider == "groq":
        url, model = "https://api.groq.com/openai/v1/chat/completions", groq_model()
    else:
        url, model = "https://api.openai.com/v1/chat/completions", OPENAI_MODEL
    body = {"model": model, "messages": [{"role": "system", "content": system or "You are a helpful assistant."},
                                         {"role": "user", "content": prompt}],
            "max_tokens": int(max_tokens), "temperature": 0.4}
    if provider == "groq":
        body.update(groq_extra(model))
        body["max_tokens"] = int(max_tokens) + 400
    raw = _post(url, {"Authorization": f"Bearer {key}"}, body, timeout)
    return str(((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def _cloud_chain(root) -> list[tuple[str, str]]:
    load_secrets(Path(root) if root else None)
    out = []
    for name, env, aliases in CLOUD:
        k = _resolve_key(env, aliases)
        if k:
            out.append((name, k))
    return out


def plan(root, cheap: bool = False) -> list[str]:
    """Provider order that complete() will try (names only)."""
    s = settings(root)
    cloud = [n for n, _ in _cloud_chain(root)]
    mode = s["ai_mode"]
    if mode == "cloud_only":
        return cloud
    if mode == "local_first" or cheap:
        return ["ollama"] + cloud
    return cloud + ["ollama"]


def complete(prompt: str, system: str = "", root=None, *, cheap: bool = False, max_tokens: int = 700,
             timeout: float = 60.0, local_timeout: float = 240.0) -> dict:
    """Returns {"ok", "text", "provider", "errors"}; never raises for provider failures."""
    if _halted():
        return {"ok": False, "halted": True, "text": "", "provider": "", "errors": ["Emergency STOP is active"]}
    s = settings(root)
    keys = dict(_cloud_chain(root))
    errors: list[str] = []
    for name in plan(root, cheap=cheap):
        if _halted():
            return {"ok": False, "halted": True, "text": "", "provider": "", "errors": errors + ["Emergency STOP is active"]}
        if name != "ollama" and cooling(name) > 0:
            errors.append(f"{name}: rate-limited (HTTP 429), skipped for {int(cooling(name))}s")
            continue
        try:
            if name == "ollama":
                if not local_llm.ready(s["local_model"]):
                    errors.append("ollama: not ready")
                    continue
                r = local_llm.chat([{"role": "user", "content": prompt}], model=s["local_model"], system=system,
                                   max_tokens=max_tokens, timeout=local_timeout)
                return {"ok": True, "text": r["text"], "provider": f"ollama:{r['model']}", "errors": errors,
                        "seconds": r["seconds"]}
            if name == "gemini":
                text = _gemini(system, prompt, keys[name], max_tokens, timeout)
            else:
                text = _openai_compat(system, prompt, keys[name], max_tokens, timeout, name)
            if text:
                return {"ok": True, "text": text, "provider": name, "errors": errors}
            errors.append(f"{name}: empty reply")
        except Exception as e:
            msg = str(e)[:120]
            if "HTTP 429" in msg:
                import time

                _cooldown[name] = time.monotonic() + COOLDOWN_S  # fall through now, skip it for a while
            errors.append(f"{name}: {msg}")
    if not errors:
        errors.append("no AI provider: add a cloud key in Settings or pull a local model in Ollama")
    return {"ok": False, "text": "", "provider": "", "errors": errors}
