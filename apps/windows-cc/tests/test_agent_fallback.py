import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import agents.worker as w  # noqa: E402
from agents.worker import AgentHub  # noqa: E402


def _oa_final(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def _oa_call(name, args, cid="c1"):
    import json
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}


def _g_call(name, args):
    return {"candidates": [{"content": {"role": "model", "parts": [
        {"functionCall": {"name": name, "args": args}, "thoughtSignature": "sig"}]}}]}


def _g_final(text):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}


def row(hub, rid):
    return next(a for a in hub.list() if a["id"] == rid)


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self._sl = mock.patch.object(w, "_sleep")
        self.sleep = self._sl.start()
        self.addCleanup(self._sl.stop)

    def test_rate_limit_retries_same_provider_first(self):
        g = mock.Mock(side_effect=[w.ProviderUnavailable("gemini", 429, '{"retryDelay": "7s"}'), _g_final("ok")])
        with mock.patch.object(w, "_gemini_turn", g):
            hub = AgentHub(root=self.root, gemini_key="g", keys={"openai": "o"})
            hub._run("memory")
        r = row(hub, "memory")
        self.assertEqual((r["last_reply"], r["provider"]), ("ok", "gemini"))
        self.sleep.assert_called_once_with(7.0)

    def test_out_of_credits_does_not_retry(self):
        g = mock.Mock(side_effect=w.ProviderUnavailable("gemini", 429, "insufficient_quota"))
        o = mock.Mock(return_value=_oa_final("fine"))
        with mock.patch.object(w, "_gemini_turn", g), mock.patch.object(w, "_openai_turn", o):
            hub = AgentHub(root=self.root, gemini_key="g", keys={"openai": "o"})
            hub._run("memory")
        self.assertEqual(g.call_count, 1)
        self.sleep.assert_not_called()

    def tearDown(self):
        self.td.cleanup()

    def test_gemini_429_falls_back_to_openai(self):
        g = mock.Mock(side_effect=w.ProviderUnavailable("gemini", 429, "RESOURCE_EXHAUSTED"))
        o = mock.Mock(return_value=_oa_final("hello from openai"))
        with mock.patch.object(w, "_gemini_turn", g), mock.patch.object(w, "_openai_turn", o):
            hub = AgentHub(root=self.root, gemini_key="g", keys={"openai": "o"})
            hub._goals["memory"] = "x"
            hub._run("memory")
        r = row(hub, "memory")
        self.assertEqual(r["last_reply"], "hello from openai")
        self.assertEqual(r["provider"], "openai")
        self.assertIn("Gemini quota exceeded (429) — using OpenAI", r["notice"])
        self.assertIn("provider: OpenAI", r["steps"])
        # Retries Gemini (rate limit) then falls back and sticks with OpenAI.
        self.assertEqual(g.call_count, 1 + w.RETRIES)

    def test_all_providers_fail_reports_reasons(self):
        g = mock.Mock(side_effect=w.ProviderUnavailable("gemini", 429, ""))
        o = mock.Mock(side_effect=w.ProviderUnavailable("openai", 429, '{"code":"insufficient_quota"}'))
        with mock.patch.object(w, "_gemini_turn", g), mock.patch.object(w, "_openai_turn", o):
            hub = AgentHub(root=self.root, gemini_key="g", keys={"openai": "o"})
            hub._run("memory")
        r = row(hub, "memory")
        self.assertEqual(r["state"], "error")
        self.assertIn("Gemini quota exceeded", r["detail"])
        self.assertIn("OpenAI out of credits", r["detail"])

    def test_openai_tool_loop_uses_same_tools_and_history(self):
        o = mock.Mock(side_effect=[_oa_call("write_file", {"path": "s/index.html", "content": "<p>x</p>"}),
                                   _oa_final("built s")])
        with mock.patch.object(w, "_openai_turn", o):
            hub = AgentHub(root=self.root, gemini_key="", keys={"openai": "o"})
            hub._goals["builder"] = "build s"
            hub._run("builder")
        r = row(hub, "builder")
        self.assertEqual(r["last_reply"], "built s")
        self.assertEqual(r["files"], ["s/index.html"])
        self.assertTrue((self.root / "workspace/s/index.html").is_file())
        msgs = o.call_args_list[1].args[1]
        self.assertEqual(msgs[1]["tool_calls"][0]["id"], "c1")
        self.assertEqual(msgs[2]["role"], "tool")
        self.assertEqual(msgs[2]["tool_call_id"], "c1")

    def test_gemini_parts_roundtrip_keep_signature(self):
        g = mock.Mock(side_effect=[_g_call("ws_list_dir", {}), _g_final("ok")])
        with mock.patch.object(w, "_gemini_turn", g):
            hub = AgentHub(root=self.root, gemini_key="g")
            hub._run("builder")
        contents = g.call_args_list[1].args[1]
        self.assertEqual(contents[1]["parts"][0].get("thoughtSignature"), "sig")
        self.assertIn("functionResponse", contents[2]["parts"][0])

    def test_role_not_allowed_tool_blocked(self):
        g = mock.Mock(side_effect=[_g_call("write_file", {"path": "a/b.txt", "content": "x"}), _g_final("ok")])
        with mock.patch.object(w, "_gemini_turn", g):
            hub = AgentHub(root=self.root, gemini_key="g")
            hub._run("research")
        self.assertFalse((self.root / "workspace/a/b.txt").exists())
        self.assertIn("blocked tool write_file", row(hub, "research")["steps"])

    def test_overwrite_halts_then_resumes_after_approval(self):
        (self.root / "workspace/s").mkdir(parents=True)
        (self.root / "workspace/s/a.txt").write_text("old")
        events = []
        g = mock.Mock(side_effect=[_g_call("write_file", {"path": "s/a.txt", "content": "new"}),
                                   _g_final("updated")])
        with mock.patch.object(w, "_gemini_turn", g):
            hub = AgentHub(root=self.root, gemini_key="g", on_event=lambda r, k, d: events.append(k))
            hub._run("builder")
            r = row(hub, "builder")
            self.assertEqual(r["pending"]["kind"], "file")
            self.assertEqual(r["pending"]["op"], "overwrite")
            self.assertEqual((self.root / "workspace/s/a.txt").read_text(), "old")
            self.assertIn("needs_approval", events)
            p = hub.take_pending("builder", r["pending"]["token"])
            res = w.AgentTools(self.root).write_file(p["path"], p["content"], confirmed=True)
            self.assertTrue(hub.resume("builder", res))
            r = hub.wait("builder", 5)
        self.assertEqual((self.root / "workspace/s/a.txt").read_text(), "new")
        self.assertEqual(r["last_reply"], "updated")
        self.assertIn("done", events)

    def test_start_busy_returns_error(self):
        hub = AgentHub(root=self.root, gemini_key="g")
        hub._state["builder"] = "active"
        r = hub.start("builder", "x")
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("busy"))


class ReasonTests(unittest.TestCase):
    def test_reasons(self):
        self.assertEqual(w._reason("gemini", 503, ""), "Gemini server error (503)")
        self.assertEqual(w._reason("openai", 401, ""), "OpenAI key rejected (401)")
        self.assertIn("unreachable", w._reason("groq", None, "URLError"))


if __name__ == "__main__":
    unittest.main()
