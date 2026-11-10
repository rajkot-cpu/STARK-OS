import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import cc_settings  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_defaults_opt_in_off(self):
        with tempfile.TemporaryDirectory() as d:
            s = cc_settings.load(d)
            self.assertFalse(s["wake_word"])
            self.assertEqual(s["stt_engine"], "auto")
            self.assertEqual(s["voice"], "en-IN-PrabhatNeural")

    def test_save_validates(self):
        with tempfile.TemporaryDirectory() as d:
            s = cc_settings.save(d, {"wake_word": "yes", "voice": "evil", "stt_engine": "whisper", "x": 1})
            self.assertFalse(s["wake_word"])  # only literal True enables
            self.assertEqual(s["voice"], "en-IN-PrabhatNeural")
            self.assertEqual(s["stt_engine"], "whisper")
            raw = json.loads((Path(d) / "config" / "cc_settings.json").read_text())
            self.assertNotIn("x", raw)
            s = cc_settings.save(d, {"wake_word": True, "voice": "en-IN-NeerjaNeural"})
            self.assertTrue(cc_settings.load(d)["wake_word"])
            self.assertEqual(cc_settings.load(d)["voice"], "en-IN-NeerjaNeural")

    def test_audit_appends(self):
        with tempfile.TemporaryDirectory() as d:
            cc_settings.audit(d, "t", "a", "r")
            cc_settings.audit(d, "t", "b", "r")
            lines = (Path(d) / "logs" / "audit.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["action"], "b")


if __name__ == "__main__":
    unittest.main()
