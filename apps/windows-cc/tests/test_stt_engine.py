import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import stt  # noqa: E402


def _fake_model(root: Path, name="tiny.en"):
    snap = root / "models" / ("models--" + stt._REPO[name].replace("/", "--")) / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "model.bin").write_bytes(b"x")
    (snap / "config.json").write_text("{}")


class FakeAudio:
    def get_raw_data(self, convert_rate=None, convert_width=None):
        assert convert_rate == 16000 and convert_width == 2
        return b"\x00\x00" * 1600


class SttEngineTests(unittest.TestCase):
    def test_model_ready_detection(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(stt.whisper_model_ready(d))
            _fake_model(Path(d))
            self.assertTrue(stt.whisper_model_ready(d))
            self.assertFalse(stt.whisper_model_ready(d, "base.en"))

    def test_choose_engine(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(stt, "whisper_installed", lambda: True):
            self.assertEqual(stt.choose_engine("auto", d), "google")
            self.assertEqual(stt.choose_engine("whisper", d), "google")
            _fake_model(Path(d))
            self.assertEqual(stt.choose_engine("auto", d), "whisper")
            self.assertEqual(stt.choose_engine("google", d), "google")

    def test_pcm_to_float(self):
        arr = stt.pcm16_to_float(b"\x00\x40" * 4)
        self.assertEqual(arr.dtype.name, "float32")
        self.assertAlmostEqual(float(arr[0]), 0.5, places=3)

    def test_whisper_path_uses_numpy(self):
        with mock.patch.object(stt, "transcribe_whisper", lambda raw, root=None, name="tiny.en": "hello sir"):
            r = stt.transcribe_audio(FakeAudio(), "whisper")
        self.assertEqual(r, {"ok": True, "text": "hello sir", "engine": "whisper"})

    def test_whisper_failure_falls_back_to_google(self):
        def boom(*a, **k):
            raise RuntimeError("no model")
        with mock.patch.object(stt, "transcribe_whisper", boom), \
             mock.patch.object(stt, "_google", lambda a: {"ok": True, "text": "g", "engine": "google"}):
            self.assertEqual(stt.transcribe_audio(FakeAudio(), "whisper")["engine"], "google")

    def test_listen_once_auto_triggers_background_download(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(stt, "whisper_installed", lambda: True), \
             mock.patch.object(stt, "download_model") as dl, \
             mock.patch.object(stt, "record_once", lambda *a: (None, {"ok": False, "error": "No speech heard — timed out"})):
            r = stt.listen_once(root=d)
            self.assertFalse(r["ok"])
            dl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
