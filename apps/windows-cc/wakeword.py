# apps/windows-cc/wakeword.py
"""'Hey Jarvis' wake word (openWakeWord, ONNX runtime only) + barge-in.

OFF by default; the operator turns it on in Settings (R3 opt-in, audited).
Detection is fully local. The mic loop runs in a background thread and is
released (paused) while a voice turn records the operator's question.
"""
from __future__ import annotations

import sys
import threading
import time
import types

FRAME = 1280  # 80 ms @ 16 kHz
RATE = 16000
THRESHOLD = 0.5
COOLDOWN_S = 2.0


def _stub_training_deps() -> None:
    """openwakeword imports scipy/sklearn only for verifier *training*.
    We exclude them from the exe; install harmless stubs when missing."""
    missing = False
    for name in ("scipy", "sklearn"):
        try:
            __import__(name)
        except Exception:
            missing = True
    if not missing:
        return  # real libs present (dev machines) — nothing to stub
    for n in ("scipy", "scipy.signal", "sklearn", "sklearn.linear_model",
              "sklearn.pipeline", "sklearn.preprocessing"):
        if sys.modules.get(n) is None:
            sys.modules[n] = types.ModuleType(n)
    sys.modules["sklearn.linear_model"].LogisticRegression = object
    sys.modules["sklearn.pipeline"].make_pipeline = lambda *a, **k: None
    sys.modules["sklearn.preprocessing"].StandardScaler = object
    sys.modules["sklearn.preprocessing"].FunctionTransformer = object


def available() -> tuple[bool, str]:
    try:
        _stub_training_deps()
        import onnxruntime  # noqa: F401
        import openwakeword  # noqa: F401
    except Exception as e:
        return False, f"openwakeword unavailable: {type(e).__name__}"
    try:
        import pyaudio  # noqa: F401
    except Exception:
        return False, "PyAudio missing (needed for mic)"
    return True, ""


class OwwDetector:
    """Thin wrapper so tests can swap in a fake."""

    def __init__(self):
        _stub_training_deps()
        import os

        import openwakeword
        from openwakeword.model import Model

        path = os.path.join(openwakeword.__path__[0], "resources", "models", "hey_jarvis_v0.1.onnx")
        self._m = Model(wakeword_model_paths=[path])

    def score(self, frame) -> float:
        p = self._m.predict(frame)
        return float(max(p.values())) if p else 0.0

    def reset(self) -> None:
        self._m.reset()


class PyAudioSource:
    def __init__(self):
        import pyaudio

        self._pa = pyaudio.PyAudio()
        self._st = self._pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                                 input=True, frames_per_buffer=FRAME)

    def read(self):
        import numpy as np

        raw = self._st.read(FRAME, exception_on_overflow=False)
        return np.frombuffer(raw, dtype=np.int16)

    def close(self) -> None:
        for fn in (getattr(self._st, "stop_stream", None), getattr(self._st, "close", None),
                   getattr(self._pa, "terminate", None)):
            try:
                fn and fn()
            except Exception:
                pass


class WakeListener:
    def __init__(self, on_wake, *, is_speaking=None, stop_speaking=None,
                 source_factory=PyAudioSource, detector_factory=OwwDetector,
                 threshold: float = THRESHOLD, cooldown: float = COOLDOWN_S):
        self.on_wake = on_wake
        self.is_speaking = is_speaking or (lambda: False)
        self.stop_speaking = stop_speaking or (lambda: False)
        self.source_factory = source_factory
        self.detector_factory = detector_factory
        self.threshold = threshold
        self.cooldown = cooldown
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = "off"
        self.error = ""
        self.wakes = 0
        self.barge_ins = 0
        self._last_wake = 0.0

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._paused.clear()
        self.error = ""
        self.state = "starting"
        self._thread = threading.Thread(target=self._loop, name="jarvis-wake", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout)
        self.state = "off"

    def pause(self) -> None:
        """Release the mic (e.g. while recording the operator's question)."""
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def _fire(self) -> None:
        self.wakes += 1
        if self.is_speaking():
            self.barge_ins += 1
            try:
                self.stop_speaking()
            except Exception:
                pass
        threading.Thread(target=self._safe_on_wake, daemon=True).start()

    def _safe_on_wake(self) -> None:
        try:
            self.on_wake()
        except Exception as e:
            self.error = f"wake handler: {type(e).__name__}: {str(e)[:120]}"

    def _loop(self) -> None:
        src = None
        try:
            det = self.detector_factory()
        except Exception as e:
            self.error = f"wake model failed: {type(e).__name__}: {str(e)[:120]}"
            self.state = "error"
            return
        try:
            while not self._stop.is_set():
                if self._paused.is_set():
                    if src is not None:
                        src.close()
                        src = None
                    self.state = "paused"
                    time.sleep(0.05)
                    continue
                if src is None:
                    try:
                        src = self.source_factory()
                        det.reset()
                    except Exception as e:
                        self.error = f"mic: {type(e).__name__}: {str(e)[:120]}"
                        self.state = "error"
                        return
                    self.state = "listening"
                frame = src.read()
                if frame is None:
                    break
                if det.score(frame) >= self.threshold:
                    now = time.monotonic()
                    if now - self._last_wake >= self.cooldown:
                        self._last_wake = now
                        det.reset()
                        self._fire()
        except Exception as e:
            self.error = f"wake loop: {type(e).__name__}: {str(e)[:120]}"
            self.state = "error"
        finally:
            if src is not None:
                src.close()
            if self.state != "error":
                self.state = "off"
