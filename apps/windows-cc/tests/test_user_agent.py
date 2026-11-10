"""Regression (2026-11-10): Groq sits behind Cloudflare, which answers 403 'error code: 1010' to the
default 'Python-urllib/x.y' User-Agent. Every API request must send an explicit User-Agent."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import agents.worker as w  # noqa: E402
import chat  # noqa: E402
import llm_providers  # noqa: E402


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(payload):
    seen = []

    def fake(req, timeout=None):
        seen.append(req)
        return _Resp(json.dumps(payload).encode())
    return seen, fake


def _ua(req):
    return req.get_header("User-agent") or ""


class UserAgentTests(unittest.TestCase):
    def test_agent_groq_turn_sends_user_agent(self):
        seen, fake = _capture({"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
        with mock.patch("urllib.request.urlopen", fake):
            w._openai_turn("sys", [], [], "k", provider="groq")
        self.assertIn("groq.com", seen[0].full_url)
        self.assertTrue(_ua(seen[0]).startswith("JARVIS"), _ua(seen[0]))

    def test_chat_groq_and_openai_send_user_agent(self):
        seen, fake = _capture({"choices": [{"message": {"content": "hi"}}]})
        with mock.patch("urllib.request.urlopen", fake):
            chat._groq_reply("hi", "k")
            chat._openai_reply("hi", "k")
        self.assertTrue(all(_ua(r).startswith("JARVIS") for r in seen), [_ua(r) for r in seen])

    def test_gemini_requests_send_user_agent(self):
        seen, fake = _capture({"candidates": [{"content": {"parts": [{"text": "hi"}]}}]})
        with mock.patch("urllib.request.urlopen", fake):
            chat._gemini_reply("hi", "k")
        self.assertTrue(_ua(seen[0]).startswith("JARVIS"))

    def test_provider_probe_sends_user_agent(self):
        seen, fake = _capture({})
        with mock.patch("urllib.request.urlopen", fake):
            llm_providers._http_json("https://api.groq.com/openai/v1/models", {"Authorization": "Bearer k"}, None, 5)
        self.assertTrue(_ua(seen[0]).startswith("JARVIS"))


class GroqModelTests(unittest.TestCase):
    """Regression (2026-11-10): llama-3.3-70b-versatile was retired on Groq (404 model not found)."""

    def _body(self, fn):
        seen, fake = _capture({"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
        with mock.patch("urllib.request.urlopen", fake):
            fn()
        return json.loads(seen[0].data)

    def test_default_groq_model_is_current_and_low_reasoning(self):
        with mock.patch.dict("os.environ", {"JARVIS_GROQ_MODEL": ""}):
            for fn in (lambda: w._openai_turn("s", [], [], "k", provider="groq"),
                       lambda: chat._groq_reply("hi", "k")):
                b = self._body(fn)
                self.assertEqual(b["model"], "openai/gpt-oss-120b")
                self.assertEqual(b["reasoning_effort"], "low")

    def test_groq_model_env_override(self):
        with mock.patch.dict("os.environ", {"JARVIS_GROQ_MODEL": "qwen/some-model"}):
            b = self._body(lambda: w._openai_turn("s", [], [], "k", provider="groq"))
            self.assertEqual(b["model"], "qwen/some-model")
            self.assertNotIn("reasoning_effort", b)

    def test_openai_body_has_no_reasoning_effort(self):
        b = self._body(lambda: w._openai_turn("s", [], [], "k", provider="openai"))
        self.assertNotIn("reasoning_effort", b)


if __name__ == "__main__":
    unittest.main()
