import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))
sys.path.insert(0, str(ROOT / "apps" / "windows-panel"))

import tts  # noqa: E402


class TtsTests(unittest.TestCase):
    def test_edge_then_play(self):
        calls = []
        with mock.patch.object(tts, "edge_synthesize", lambda t, v, p, timeout=8: calls.append(("synth", v))), \
             mock.patch.object(tts, "play_file_interruptible", lambda p, s: calls.append(("play", p)) or True), \
             mock.patch.object(tts, "_muted", lambda: False):
            self.assertEqual(tts.speak("hello", "en-IN-NeerjaNeural", wait=True), "edge")
        self.assertEqual(calls[0], ("synth", "en-IN-NeerjaNeural"))
        self.assertEqual(calls[1][0], "play")
        self.assertFalse(Path(calls[1][1]).exists(), "temp mp3 must be deleted")

    def test_offline_falls_back_to_sapi(self):
        def boom(*a, **k):
            raise OSError("offline")
        with mock.patch.object(tts, "edge_synthesize", boom), \
             mock.patch.object(tts, "sapi_speak_interruptible", lambda t, s: True), \
             mock.patch.object(tts, "_muted", lambda: False):
            self.assertEqual(tts.speak("hello", wait=True), "sapi")

    def test_sapi_choice_skips_edge(self):
        with mock.patch.object(tts, "edge_synthesize", side_effect=AssertionError("no edge")), \
             mock.patch.object(tts, "sapi_speak_interruptible", lambda t, s: True), \
             mock.patch.object(tts, "_muted", lambda: False):
            self.assertEqual(tts.speak("hello", "sapi", wait=True), "sapi")

    def test_stop_interrupts_playback(self):
        started = threading.Event()
        result = {}

        def fake_play(path, should_stop):
            started.set()
            for _ in range(200):
                if should_stop():
                    result["stopped"] = True
                    return False
                time.sleep(0.01)
            return True

        with mock.patch.object(tts, "edge_synthesize", lambda *a, **k: None), \
             mock.patch.object(tts, "play_file_interruptible", fake_play), \
             mock.patch.object(tts, "_muted", lambda: False):
            tts.speak("long reply", wait=False)
            self.assertTrue(started.wait(2))
            self.assertTrue(tts.is_speaking())
            self.assertTrue(tts.stop())
            for _ in range(100):
                if not tts.is_speaking():
                    break
                time.sleep(0.01)
        self.assertTrue(result.get("stopped"))
        self.assertFalse(tts.is_speaking())

    def test_muted_is_silent(self):
        with mock.patch.object(tts, "_muted", lambda: True), \
             mock.patch.object(tts, "edge_synthesize", side_effect=AssertionError("no")):
            self.assertEqual(tts.speak("x", wait=True), "muted")


if __name__ == "__main__":
    unittest.main()
