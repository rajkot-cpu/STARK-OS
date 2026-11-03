# apps/windows-cc/stt.py
from __future__ import annotations


def listen_once(timeout: float = 5.0, phrase_time_limit: float = 8.0) -> dict:
    try:
        import speech_recognition as sr
    except Exception as e:
        return {"ok": False, "error": f"speech_recognition missing: {e}"}
    try:
        import pyaudio  # noqa: F401
    except Exception as e:
        return {
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
        try:
            text = rec.recognize_google(audio, language="en-IN")
        except sr.UnknownValueError:
            return {"ok": False, "error": "Could not understand audio — try again closer to the mic"}
        except sr.RequestError as e:
            return {"ok": False, "error": f"Speech service unavailable: {e}"}
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "Empty transcript"}
        return {"ok": True, "text": text}
    except sr.WaitTimeoutError:
        return {"ok": False, "error": "No speech heard — timed out"}
    except OSError as e:
        return {"ok": False, "error": f"Microphone error: {e}"}
    except Exception as e:
        msg = str(e).strip() or type(e).__name__
        return {"ok": False, "error": msg}
