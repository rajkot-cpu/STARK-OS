# apps/windows-cc/stt.py
"""Speech-to-text: offline faster-whisper (default when its model is on disk)
with Google speech_recognition as the online fallback.

Whisper models are NOT bundled; they download on first use into <root>/models.
Audio is passed to faster-whisper as a float32 numpy array (av 19 file-decode bug).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

_models: dict = {}
_models_lock = threading.Lock()
_download_lock = threading.Lock()
_downloading: set = set()
_download_error: dict = {}

_REPO = {"tiny.en": "Systran/faster-whisper-tiny.en", "base.en": "Systran/faster-whisper-base.en"}


def models_dir(root: Path | str | None) -> Path:
    if root is None:
        root = os.environ.get("JARVIS_HOME") or "."
    return Path(root) / "models"


def whisper_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def whisper_model_ready(root, name: str = "tiny.en") -> bool:
    """True when the model files are already on disk (no network needed)."""
    repo = _REPO.get(name)
    if not repo:
        return False
    base = models_dir(root) / ("models--" + repo.replace("/", "--")) / "snapshots"
    if not base.is_dir():
        return False
    for snap in base.iterdir():
        if (snap / "model.bin").is_file() and (snap / "config.json").is_file():
            return True
    return False


def whisper_status(root, name: str = "tiny.en") -> dict:
    return {
        "installed": whisper_installed(),
        "model": name,
        "ready": whisper_model_ready(root, name),
        "downloading": name in _downloading,
        "error": _download_error.get(name, ""),
        "dir": str(models_dir(root)),
    }


def _load_model(root, name: str, allow_download: bool):
    key = (str(models_dir(root)), name)
    with _models_lock:
        if key in _models:
            return _models[key]
        from faster_whisper import WhisperModel

        d = models_dir(root)
        d.mkdir(parents=True, exist_ok=True)
        m = WhisperModel(
            name,
            device="cpu",
            compute_type="int8",
            download_root=str(d),
            local_files_only=not allow_download,
        )
        _models[key] = m
        return m


def download_model(root, name: str = "tiny.en", background: bool = True) -> dict:
    """Fetch the whisper model into <root>/models (first use). Never bundled."""
    if name not in _REPO:
        return {"ok": False, "error": "unknown model"}
    if not whisper_installed():
        return {"ok": False, "error": "faster-whisper not installed"}
    if whisper_model_ready(root, name):
        return {"ok": True, "data": whisper_status(root, name)}

    def run():
        with _download_lock:
            if whisper_model_ready(root, name):
                return
            _downloading.add(name)
            _download_error.pop(name, None)
            try:
                _load_model(root, name, allow_download=True)
            except Exception as e:
                _download_error[name] = f"{type(e).__name__}: {str(e)[:160]}"
            finally:
                _downloading.discard(name)

    if background:
        if name not in _downloading:
            threading.Thread(target=run, daemon=True).start()
    else:
        run()
    return {"ok": True, "data": whisper_status(root, name)}


def pcm16_to_float(raw: bytes):
    import numpy as np

    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_whisper(pcm16_mono_16k: bytes, root=None, name: str = "tiny.en") -> str:
    model = _load_model(root, name, allow_download=False)
    audio = pcm16_to_float(pcm16_mono_16k)
    segments, _info = model.transcribe(
        audio, language="en", beam_size=1, condition_on_previous_text=False
    )
    return " ".join(s.text for s in segments).strip()


def choose_engine(setting: str, root, name: str = "tiny.en") -> str:
    """Resolve 'auto' to whisper when its model is on disk, else google."""
    setting = (setting or "auto").lower()
    ready = whisper_installed() and whisper_model_ready(root, name)
    if setting == "google":
        return "google"
    if setting == "whisper":
        return "whisper" if ready else "google"
    return "whisper" if ready else "google"


def record_once(timeout: float = 5.0, phrase_time_limit: float = 8.0):
    """Returns (audio, None) or (None, error_dict)."""
    try:
        import speech_recognition as sr
    except Exception as e:
        return None, {"ok": False, "error": f"speech_recognition missing: {e}"}
    try:
        import pyaudio  # noqa: F401
    except Exception as e:
        return None, {
            "ok": False,
            "error": f"PyAudio missing (needed for mic): {e}. Run: python -m pip install pyaudio",
        }
    rec = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            try:
                rec.adjust_for_ambient_noise(source, duration=0.4)
            except Exception:
                pass
            audio = rec.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        return audio, None
    except sr.WaitTimeoutError:
        return None, {"ok": False, "error": "No speech heard — timed out"}
    except OSError as e:
        return None, {"ok": False, "error": f"Microphone error: {e}"}
    except Exception as e:
        return None, {"ok": False, "error": str(e).strip() or type(e).__name__}


def _google(audio) -> dict:
    import speech_recognition as sr

    try:
        text = audio and sr.Recognizer().recognize_google(audio, language="en-IN")
    except sr.UnknownValueError:
        return {"ok": False, "error": "Could not understand audio — try again closer to the mic"}
    except sr.RequestError as e:
        return {"ok": False, "error": f"Speech service unavailable: {e}"}
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Empty transcript"}
    return {"ok": True, "text": text, "engine": "google"}


def transcribe_audio(audio, engine: str, root=None, name: str = "tiny.en") -> dict:
    if engine == "whisper":
        try:
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            text = transcribe_whisper(raw, root=root, name=name)
            if text:
                return {"ok": True, "text": text, "engine": "whisper"}
            return {"ok": False, "error": "Could not understand audio — try again closer to the mic"}
        except Exception:
            # Model/runtime problem: fall back to the online engine.
            pass
    try:
        return _google(audio)
    except Exception as e:
        return {"ok": False, "error": str(e).strip() or type(e).__name__}


def listen_once(
    timeout: float = 5.0,
    phrase_time_limit: float = 8.0,
    root=None,
    engine: str | None = None,
    model: str = "tiny.en",
) -> dict:
    """Record one utterance and transcribe it (offline whisper preferred)."""
    if engine is None:
        engine = "auto"
        if root is not None:
            try:
                from cc_settings import load

                s = load(root)
                engine, model = s["stt_engine"], s["whisper_model"]
            except Exception:
                pass
    chosen = choose_engine(engine, root, model)
    if engine in ("auto", "whisper") and chosen == "google" and root is not None:
        # First use: fetch the offline model in the background for next time.
        if whisper_installed():
            download_model(root, model, background=True)
    audio, err = record_once(timeout, phrase_time_limit)
    if err:
        return err
    return transcribe_audio(audio, chosen, root=root, name=model)
