"""JARVIS voice: Windows SAPI TTS (pyttsx3 -> win32com SAPI -> silent no-op)."""
import json
import threading
from pathlib import Path

_lock = threading.Lock()
_muted = False
_prefs: Path | None = None


def _speak_sync(text: str) -> None:
    with _lock:
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.say(text)
            eng.runAndWait()
            return
        except Exception:
            pass
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            import win32com.client
            win32com.client.Dispatch("SAPI.SpVoice").Speak(text)
            return
        except Exception:
            pass
        try:
            import subprocess
            # PowerShell SAPI — works even when pyttsx3/win32com fail inside frozen exe
            safe = text.replace("'", "''")
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('%s')" % safe,
                ],
                check=False,
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass


def speak(text: str, wait: bool = False) -> None:
    """Speak a short line (1-2 sentences). Non-blocking by default; never raises."""
    if _muted or not text:
        return
    text = text.strip()[:200]
    if wait:
        _speak_sync(text)
    else:
        threading.Thread(target=_speak_sync, args=(text,), daemon=True).start()


def load_prefs(root: Path) -> None:
    global _muted, _prefs
    _prefs = Path(root) / "logs" / "panel-ui.json"
    try:
        _muted = bool(json.loads(_prefs.read_text(encoding="utf-8")).get("muted", False))
    except Exception:
        _muted = False


def is_muted() -> bool:
    return _muted


def set_muted(value: bool) -> None:
    global _muted
    _muted = bool(value)
    if _prefs is None:
        return
    try:
        data = {}
        if _prefs.exists():
            data = json.loads(_prefs.read_text(encoding="utf-8"))
        data["muted"] = _muted
        _prefs.parent.mkdir(parents=True, exist_ok=True)
        _prefs.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
