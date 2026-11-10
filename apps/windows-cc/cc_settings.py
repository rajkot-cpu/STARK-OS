# apps/windows-cc/cc_settings.py
"""Command Center settings (non-secret) + audit helper.

Settings live in <root>/config/cc_settings.json. Opt-in features default OFF.
Never store or log secret values here.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_lock = threading.Lock()

VOICES = (
    {"id": "en-IN-PrabhatNeural", "label": "Prabhat (Indian English, male)"},
    {"id": "en-IN-NeerjaNeural", "label": "Neerja (Indian English, female)"},
    {"id": "sapi", "label": "Windows voice (offline)"},
)
STT_ENGINES = (
    {"id": "auto", "label": "Auto (offline when model is ready)"},
    {"id": "whisper", "label": "Offline (faster-whisper)"},
    {"id": "google", "label": "Online (Google)"},
)
WHISPER_MODELS = ("tiny.en", "base.en")

DEFAULTS: dict = {
    "wake_word": False,
    "stt_engine": "auto",
    "whisper_model": "tiny.en",
    "voice": "en-IN-PrabhatNeural",
}


def settings_path(root: Path | str) -> Path:
    return Path(root) / "config" / "cc_settings.json"


def load(root: Path | str) -> dict:
    out = dict(DEFAULTS)
    try:
        raw = json.loads(settings_path(root).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k in DEFAULTS:
                if k in raw:
                    out[k] = raw[k]
    except Exception:
        pass
    return _validated(out)


def _validated(s: dict) -> dict:
    out = dict(DEFAULTS)
    out["wake_word"] = bool(s.get("wake_word") is True)
    if s.get("stt_engine") in {e["id"] for e in STT_ENGINES}:
        out["stt_engine"] = s["stt_engine"]
    if s.get("whisper_model") in WHISPER_MODELS:
        out["whisper_model"] = s["whisper_model"]
    if s.get("voice") in {v["id"] for v in VOICES}:
        out["voice"] = s["voice"]
    return out


def save(root: Path | str, updates: dict) -> dict:
    """Merge known keys, validate, persist. Unknown keys / bad values are ignored."""
    with _lock:
        cur = load(root)
        merged = dict(cur)
        for k, v in (updates or {}).items():
            if k in DEFAULTS:
                merged[k] = v
        merged = _validated(merged)
        p = settings_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged


def audit(root: Path | str, task: str, action: str, result: str, undo: str = "") -> None:
    """Append one line to logs/audit.jsonl (same shape as the rest of Jarvis)."""
    try:
        p = Path(root) / "logs" / "audit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        line = {
            "time": datetime.now(_IST).isoformat(timespec="seconds"),
            "task": task,
            "action": action,
            "result": str(result)[:300],
            "undo": undo,
        }
        with _lock, p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass
