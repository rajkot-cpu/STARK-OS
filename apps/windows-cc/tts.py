# apps/windows-cc/tts.py
"""Natural voice (edge-tts, online) with interruptible playback.

Order: edge-tts neural voice (en-IN) -> Windows SAPI (offline) -> voice.speak.
`stop()` interrupts whatever is playing (stop button / "Hey Jarvis" barge-in).
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

_state_lock = threading.Lock()
_stop_evt = threading.Event()
_speaking = threading.Event()
_gen = 0  # increments per utterance; older utterances abort
_last_engine = ""
_last_error = ""

EDGE_TIMEOUT = 8.0


def is_speaking() -> bool:
    return _speaking.is_set()


def last_engine() -> str:
    return _last_engine


def stop() -> bool:
    """Interrupt current playback. Returns True if something was playing."""
    was = _speaking.is_set()
    _stop_evt.set()
    return was


def _muted() -> bool:
    try:
        import voice

        return bool(voice.is_muted())
    except Exception:
        return False


def edge_synthesize(text: str, voice_id: str, out_path: str, timeout: float = EDGE_TIMEOUT) -> None:
    import asyncio

    import edge_tts

    async def _run():
        import aiohttp

        # ThreadedResolver: aiodns (if installed) needs a SelectorEventLoop on Windows.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        try:
            comm = edge_tts.Communicate(text, voice_id, connector=connector)
            await asyncio.wait_for(comm.save(out_path), timeout=timeout)
        finally:
            await connector.close()

    asyncio.run(_run())
    if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("edge-tts produced no audio")


def _mci(cmd: str) -> int:
    import ctypes

    buf = ctypes.create_unicode_buffer(256)
    return ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, 0)


def play_file_interruptible(path: str, should_stop) -> bool:
    """Play an mp3 via Windows MCI; poll should_stop(). Returns False if interrupted."""
    if not sys.platform.startswith("win"):
        raise RuntimeError("mp3 playback needs Windows")
    alias = f"jarvis{threading.get_ident()}"
    if _mci(f'open "{path}" type mpegvideo alias {alias}') != 0:
        raise RuntimeError("MCI open failed")
    try:
        if _mci(f"play {alias}") != 0:
            raise RuntimeError("MCI play failed")
        import ctypes

        buf = ctypes.create_unicode_buffer(64)
        while True:
            if should_stop():
                _mci(f"stop {alias}")
                return False
            ctypes.windll.winmm.mciSendStringW(f"status {alias} mode", buf, 63, 0)
            if buf.value.lower() not in ("playing", "seeking", ""):
                return True
            time.sleep(0.05)
    finally:
        _mci(f"close {alias}")


def sapi_speak_interruptible(text: str, should_stop) -> bool:
    """SAPI async speak with purge-on-stop. Returns False if interrupted."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    v = win32com.client.Dispatch("SAPI.SpVoice")
    v.Speak(text, 1)  # SVSFlagsAsync
    while not v.WaitUntilDone(80):
        if should_stop():
            v.Speak("", 3)  # async + purge
            return False
    return True


def _speak_blocking(text: str, voice_id: str, my_gen: int) -> str:
    global _last_engine, _last_error

    def should_stop() -> bool:
        return _stop_evt.is_set() or my_gen != _gen

    if voice_id and voice_id != "sapi":
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(prefix="jarvis_tts_", suffix=".mp3")
            os.close(fd)
            edge_synthesize(text, voice_id, tmp)
            if should_stop():
                return "interrupted"
            play_file_interruptible(tmp, should_stop)
            _last_engine = "edge"
            return "edge"
        except Exception as e:  # offline / blocked / not Windows
            _last_error = f"edge: {type(e).__name__}"
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    if should_stop():
        return "interrupted"
    try:
        sapi_speak_interruptible(text, should_stop)
        _last_engine = "sapi"
        return "sapi"
    except Exception as e:
        _last_error = f"sapi: {type(e).__name__}"
    try:
        import voice

        voice.speak(text, wait=True)
        _last_engine = "voice"
        return "voice"
    except Exception:
        return "none"


def speak(text: str, voice_id: str = "en-IN-PrabhatNeural", wait: bool = False):
    """Speak text with the chosen voice; a new utterance interrupts the previous one."""
    global _gen
    text = (text or "").strip()[:600]
    if not text or _muted():
        return "muted" if text else "empty"
    with _state_lock:
        _gen += 1
        my_gen = _gen
        _stop_evt.clear()

    def run():
        _speaking.set()
        try:
            return _speak_blocking(text, voice_id, my_gen)
        finally:
            if my_gen == _gen:
                _speaking.clear()

    if wait:
        return run()
    threading.Thread(target=run, daemon=True).start()
    return "started"


def voice_choices() -> list[dict]:
    from cc_settings import VOICES

    return [dict(v) for v in VOICES]


def edge_available() -> bool:
    try:
        import edge_tts  # noqa: F401

        return True
    except Exception:
        return False
