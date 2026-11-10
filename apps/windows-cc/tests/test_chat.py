import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import chat  # noqa: E402


class ChatFallbackTests(unittest.TestCase):
    def _env(self, **keys):
        base = {k: "" for k in ("JARVIS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                                "JARVIS_OPENAI_API_KEY", "OPENAI_API_KEY", "JARVIS_GROQ_API_KEY", "GROQ_API_KEY")}
        base.update(keys)
        return mock.patch.dict(os.environ, base)

    def test_falls_back_to_groq_when_gemini_and_openai_fail(self):
        with self._env(JARVIS_GEMINI_API_KEY="g", JARVIS_OPENAI_API_KEY="o", JARVIS_GROQ_API_KEY="q"), \
                mock.patch.object(chat, "load_secrets"), \
                mock.patch.object(chat, "_gemini_reply", side_effect=RuntimeError("Gemini HTTP 429")), \
                mock.patch.object(chat, "_openai_reply", side_effect=RuntimeError("insufficient_quota")), \
                mock.patch.object(chat, "_groq_reply", return_value="Hello from Groq") as gq:
            r = chat.reply("hi", root=Path("."))
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["data"]["reply"], r["data"]["provider"]), ("Hello from Groq", "groq"))
        gq.assert_called_once()

    def test_groq_only_key_is_enough(self):
        with self._env(JARVIS_GROQ_API_KEY="q"), mock.patch.object(chat, "load_secrets"), \
                mock.patch.object(chat, "_groq_reply", return_value="ok"):
            r = chat.reply("hi", root=Path("."))
        self.assertEqual(r["data"]["provider"], "groq")

    def test_system_prompt_forbids_claiming_builds(self):
        s = chat.SYSTEM.lower()
        self.assertIn("cannot build", s)
        self.assertIn("build me", s)


if __name__ == "__main__":
    unittest.main()
