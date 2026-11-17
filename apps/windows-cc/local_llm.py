# apps/windows-cc/local_llm.py
"""Local AI via Ollama (Phase 3). Loopback only; never pulls, installs or starts anything.

Adapted from the v7 bundle's local_llm_engine.py (loopback generate + model list); the v7
auto-`ollama serve` and in-app pull were dropped — pulling a model is an operator action.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

DEFAULT_MODEL = "jarvis-local"   # Modelfile: FROM qwen2.5:3b, num_gpu 0, num_ctx 8192 (ollama/jarvis-local.Modelfile)
BASE_MODEL = "qwen2.5:3b"
_MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,79}$")
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_CACHE: dict = {"ts": 0.0, "models": None, "err": ""}


def base_url() -> str:
    """JARVIS_OLLAMA_BASE if it points at this PC, else the default loopback port."""
    raw = (os.environ.get("JARVIS_OLLAMA_BASE") or "").strip().rstrip("/")
    if raw:
        try:
            if (urlparse(raw).hostname or "") in _LOOPBACK:
                return raw
        except Exception:
            pass
    return "http://127.0.0.1:11434"


def valid_model(name: str) -> bool:
    return bool(_MODEL_RE.match(str(name or "")))


def models(timeout: float = 1.5, max_age: float = 15.0) -> list[str] | None:
    """Installed model names, or None when Ollama is not reachable. Cached briefly."""
    now = time.time()
    if _CACHE["models"] is not None and now - _CACHE["ts"] < max_age:
        return list(_CACHE["models"])
    try:
        with urllib.request.urlopen(base_url() + "/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        names = [str(m.get("name") or "") for m in (data.get("models") or []) if m.get("name")]
        _CACHE.update(ts=now, models=names, err="")
        return list(names)
    except Exception as e:
        _CACHE.update(ts=now, models=None, err=type(e).__name__)
        return None


def clear_cache() -> None:
    _CACHE.update(ts=0.0, models=None, err="")


def resolve_model(wanted: str = "") -> str:
    """The configured model if installed; else the first installed model; else ''."""
    names = models() or []
    wanted = wanted if valid_model(wanted) else DEFAULT_MODEL
    if wanted in names:
        return wanted
    if ":" not in wanted and f"{wanted}:latest" in names:
        return f"{wanted}:latest"
    for alt in (f"{DEFAULT_MODEL}:latest", BASE_MODEL):
        if alt in names:
            return alt
    return names[0] if names else ""


def status(wanted: str = "") -> dict:
    names = models()
    if names is None:
        return {"state": "not_running", "models": [], "model": "", "base": base_url()}
    if not names:
        return {"state": "no_models", "models": [], "model": "", "base": base_url()}
    return {"state": "ready", "models": names, "model": resolve_model(wanted), "base": base_url()}


def ready(wanted: str = "") -> bool:
    return bool(resolve_model(wanted))


def chat(messages: list[dict], *, model: str = "", system: str = "", max_tokens: int = 400,
         temperature: float = 0.3, timeout: float = 180.0, json_mode: bool = False) -> dict:
    """One non-streaming /api/chat call. Returns {"text", "model", "eval_count", "seconds"}."""
    m = resolve_model(model)
    if not m:
        raise RuntimeError("Ollama not ready (not running or no model pulled)")
    msgs = ([{"role": "system", "content": system}] if system else []) + list(messages)
    body = {"model": m, "messages": msgs, "stream": False, "keep_alive": "10m",
            "options": {"num_predict": int(max_tokens), "temperature": float(temperature)}}
    if os.environ.get("JARVIS_OLLAMA_GPU") != "1":
        body["options"]["num_gpu"] = 0  # GTX 1050 2 GB: Ollama's CUDA runner crashes; CPU is reliable
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(base_url() + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Ollama unreachable ({type(e).__name__})") from e
    text = str((raw.get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned an empty reply")
    return {"text": text, "model": m, "eval_count": int(raw.get("eval_count") or 0),
            "seconds": round(time.time() - t0, 2)}


def generate(prompt: str, **kw) -> str:
    return chat([{"role": "user", "content": str(prompt)}], **kw)["text"]
