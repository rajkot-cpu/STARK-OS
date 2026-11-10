import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import wakeword  # noqa: E402


class FakeSource:
    instances = []

    def __init__(self, scores):
        self.scores = list(scores)
        self.closed = False
        FakeSource.instances.append(self)

    def read(self):
        time.sleep(0.002)
        return self.scores.pop(0) if self.scores else 0.0

    def close(self):
        self.closed = True


class FakeDet:
    def score(self, frame):
        return float(frame)

    def reset(self):
        pass


def _wait(pred, t=2.0):
    end = time.time() + t
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


class WakeTests(unittest.TestCase):
    def test_detect_fires_once_with_cooldown(self):
        woke = []
        lst = wakeword.WakeListener(lambda: woke.append(1),
                                    source_factory=lambda: FakeSource([0.1, 0.9, 0.95, 0.2]),
                                    detector_factory=FakeDet, cooldown=10)
        lst.start()
        self.assertTrue(_wait(lambda: woke))
        lst.stop()
        self.assertEqual(len(woke), 1)
        self.assertFalse(lst.running)

    def test_barge_in_stops_tts(self):
        stopped = threading.Event()
        lst = wakeword.WakeListener(lambda: None, is_speaking=lambda: True,
                                    stop_speaking=stopped.set,
                                    source_factory=lambda: FakeSource([0.99]),
                                    detector_factory=FakeDet)
        lst.start()
        self.assertTrue(stopped.wait(2))
        lst.stop()
        self.assertEqual(lst.barge_ins, 1)

    def test_pause_releases_mic_and_stop_is_clean(self):
        FakeSource.instances.clear()
        lst = wakeword.WakeListener(lambda: None, source_factory=lambda: FakeSource([0.0] * 10000),
                                    detector_factory=FakeDet)
        lst.start()
        self.assertTrue(_wait(lambda: lst.state == "listening"))
        lst.pause()
        self.assertTrue(_wait(lambda: lst.state == "paused"))
        self.assertTrue(FakeSource.instances[0].closed)
        lst.resume()
        self.assertTrue(_wait(lambda: lst.state == "listening"))
        lst.stop()
        self.assertFalse(lst.running)
        self.assertTrue(all(s.closed for s in FakeSource.instances))

    def test_mic_error_reported(self):
        def bad():
            raise OSError("no mic")
        lst = wakeword.WakeListener(lambda: None, source_factory=bad, detector_factory=FakeDet)
        lst.start()
        self.assertTrue(_wait(lambda: not lst.running))
        self.assertEqual(lst.state, "error")
        self.assertIn("mic", lst.error)


if __name__ == "__main__":
    unittest.main()


class StubTests(unittest.TestCase):
    def test_real_model_loads_without_scipy_sklearn(self):
        import subprocess
        code = (
            "import sys\n"
            "for n in ('scipy','sklearn'): sys.modules[n]=None\n"
            "import wakeword, numpy as np\n"
            "ok, why = wakeword.available()\n"
            "d = wakeword.OwwDetector()\n"
            "print('SCORE', d.score(np.zeros(1280, dtype=np.int16)))\n"
        )
        try:
            import openwakeword  # noqa: F401
        except Exception:
            self.skipTest("openwakeword not installed")
        r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT / "apps" / "windows-cc"),
                           capture_output=True, text=True, timeout=60)
        self.assertIn("SCORE", r.stdout, r.stderr[-800:])
