import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
for p in ("apps/windows-cc", "apps/windows-panel", "scripts/win"):
    sys.path.insert(0, str(ROOT / p))

import agents.worker as w  # noqa: E402
from agents.worker import AgentHub  # noqa: E402
from bridge_api import BridgeApi  # noqa: E402


def _api(d):
    api = BridgeApi.__new__(BridgeApi)
    api.root = Path(d)
    api._hub = AgentHub(root=Path(d), gemini_key="g")
    api._hub.on_event = None
    api.speak = mock.Mock(return_value={"ok": True})
    return api


class CommandTests(unittest.TestCase):
    def test_build_command_starts_builder_immediately(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            with mock.patch.object(api._hub, "start", return_value={"ok": True}) as st:
                r = api.command("Jarvis, build me a hello world page called test-site")
            self.assertTrue(r["ok"])
            self.assertEqual(r["data"]["routed"], "agent")
            self.assertEqual(r["data"]["role"], "builder")
            st.assert_called_once()
            self.assertEqual(st.call_args.args[0], "builder")
            self.assertIn("Build me a hello world page called test-site", st.call_args.kwargs["goal"])
            self.assertTrue(r["data"]["reply"].startswith("On it. Builder is building"))
            self.assertIn("agent_start_by_command", (Path(d) / "logs/audit.jsonl").read_text())

    def test_busy_agent_reports(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            api._hub._state["builder"] = "active"
            r = api.command("build a snake game")
            self.assertFalse(r["data"]["started"])
            self.assertIn("busy", r["data"]["reply"])

    def test_chat_fallthrough(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            with mock.patch("chat.reply", return_value={"ok": True, "data": {"reply": "4", "provider": "gemini"}}):
                r = api.command("what is two plus two")
            self.assertEqual(r["data"]["routed"], "chat")
            self.assertEqual(r["data"]["reply"], "4")

    def test_trading_reserved_does_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            with mock.patch.object(api._hub, "start") as st, mock.patch("chat.reply") as ch:
                r = api.command("Jarvis start trading")
            st.assert_not_called()
            ch.assert_not_called()
            self.assertEqual(r["data"]["routed"], "start_trading")

    def test_tool_confirm_file_overwrite_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            ws = Path(d) / "workspace/s"
            ws.mkdir(parents=True)
            (ws / "a.txt").write_text("old")
            g = mock.Mock(side_effect=[
                {"candidates": [{"content": {"parts": [{"functionCall": {"name": "write_file",
                    "args": {"path": "s/a.txt", "content": "new"}}}]}}]},
                {"candidates": [{"content": {"parts": [{"text": "done"}]}}]}])
            with mock.patch.object(w, "_gemini_turn", g):
                api._hub._run("builder")
                tok = api._hub.pending("builder")["token"]
                self.assertFalse(api.tool_confirm("builder", "wrong")["ok"])
                r = api.tool_confirm("builder", tok)
                self.assertTrue(r["ok"], r)
                row = api._hub.wait("builder", 5)
            self.assertEqual((ws / "a.txt").read_text(), "new")
            self.assertEqual(row["last_reply"], "done")

    def test_shell_confirm_uses_workspace_cwd_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            (Path(d) / "workspace/s").mkdir(parents=True)
            g = mock.Mock(side_effect=[
                {"candidates": [{"content": {"parts": [{"functionCall": {"name": "shell",
                    "args": {"cmd": "python -m unittest", "cwd": "s"}}}]}}]},
                {"candidates": [{"content": {"parts": [{"text": "tests ran"}]}}]}])
            with mock.patch.object(w, "_gemini_turn", g):
                api._hub._run("builder")
                self.assertTrue(api._hub._detail["builder"].startswith("needs_r3:python -m unittest"))
                self.assertEqual(api._hub.pending_shell_cwd("builder"), "s")
                with mock.patch("agent_tools.AgentTools.shell", return_value={"ok": True, "data": {}}) as sh:
                    api.shell_confirm("python -m unittest", "builder")
                self.assertEqual(sh.call_args.kwargs["cwd"], "s")
                self.assertTrue(sh.call_args.kwargs["confirmed"])
                row = api._hub.wait("builder", 5)
            self.assertEqual(row["last_reply"], "tests ran")

    def test_agent_event_writes_feed_and_speaks(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            api._on_agent_event("builder", "done", {"name": "Builder", "last_reply": "Built it. Open index.html.",
                                                     "files": ["s/index.html"], "provider": "gemini"})
            self.assertIn("agent_done", (Path(d) / "logs/audit.jsonl").read_text())
            said = api.speak.call_args.args[0]
            self.assertIn("Builder finished", said)
            self.assertIn("Created 1 file", said)
            self.assertNotIn("`", said)

    def test_speakable(self):
        from bridge_api import _speakable
        self.assertEqual(_speakable("The `memory/` folder: **a** [doc](https://x.y)"), "The memory/ folder: a doc")
        self.assertLessEqual(len(_speakable("word " * 200)), 201)


if __name__ == "__main__":
    unittest.main()
