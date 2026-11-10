import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
for p in ("apps/windows-cc", "apps/windows-panel", "scripts/win"):
    sys.path.insert(0, str(ROOT / p))

from bridge_api import BridgeApi  # noqa: E402
from agents.worker import AgentHub  # noqa: E402
import agents.worker as worker  # noqa: E402


def _api(d: str) -> BridgeApi:
    api = BridgeApi.__new__(BridgeApi)
    api.root = Path(d)
    api._hub = AgentHub(root=Path(d), gemini_key="k")
    api._wake = None
    import threading
    api._wake_busy = threading.Lock()
    api._wake_info = {"state": "idle", "heard": "", "reply": "", "error": "", "engine": ""}
    return api


def _audit(d):
    p = Path(d) / "logs" / "audit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def _fn_call(name, args):
    return {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}}]}


def _wait_standby(hub, rid):
    for _ in range(200):
        if hub._state[rid] != "active":
            return
        time.sleep(0.01)


class WakeSettingTests(unittest.TestCase):
    def test_wake_on_requires_r3_and_is_audited(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            r = api.settings_set({"wake_word": True})
            self.assertFalse(r["ok"])
            self.assertIn("R3", r["error"])
            with mock.patch.object(api, "_wake_start", lambda: {"ok": True}):
                r = api.settings_set({"wake_word": True}, True)
            self.assertTrue(r["ok"], r)
            self.assertTrue(r["data"]["settings"]["wake_word"])
            self.assertIn("wake_word_on", [a["action"] for a in _audit(d)])
            r = api.settings_set({"wake_word": False})
            self.assertFalse(r["data"]["settings"]["wake_word"])
            self.assertIn("wake_word_off", [a["action"] for a in _audit(d)])

    def test_default_off_and_autostart_noop(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            g = api.settings_get()
            self.assertTrue(g["ok"], g)
            self.assertFalse(g["data"]["settings"]["wake_word"])
            self.assertEqual(g["data"]["mcp"]["servers"], [])
            with mock.patch.object(api, "_wake_start", side_effect=AssertionError("must not start")):
                self.assertTrue(api.autostart()["ok"])

    def test_wake_unavailable_not_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            with mock.patch.object(api, "_wake_start", lambda: {"ok": False, "error": "no mic"}):
                r = api.settings_set({"wake_word": True}, True)
            self.assertFalse(r["ok"])
            self.assertFalse(api.settings_get()["data"]["settings"]["wake_word"])

    def test_voice_setting(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            r = api.settings_set({"voice": "en-IN-NeerjaNeural", "stt_engine": "google"})
            self.assertEqual(r["data"]["settings"]["voice"], "en-IN-NeerjaNeural")
            self.assertEqual(api._voice_id(), "en-IN-NeerjaNeural")

    def test_on_wake_runs_voice_turn_and_speaks(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            spoken = []
            with mock.patch("stt.listen_once", lambda **k: {"ok": True, "text": "time?", "engine": "whisper"}), \
                 mock.patch("chat.reply", lambda t, root=None: {"ok": True, "data": {"reply": "Noon, sir."}}), \
                 mock.patch("tts.speak", lambda t, v, wait=False: spoken.append(t)):
                api._on_wake()
            self.assertEqual(spoken, ["Noon, sir."])
            self.assertEqual(api._wake_info["heard"], "time?")
            self.assertEqual(api._wake_info["state"], "idle")


class ScreenBridgeTests(unittest.TestCase):
    def test_screen_requires_confirm_and_audits(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            self.assertFalse(api.screen_read("q")["ok"])
            self.assertFalse(api.screen_read("q", "true")["ok"])  # only literal True
            with mock.patch.object(api, "_keys", lambda: ("g", "")), \
                 mock.patch("screen.read_screen", lambda q, **k: {"ok": True, "data": {"description": "IDE"}}):
                r = api.screen_read("q", True)
            self.assertTrue(r["ok"])
            self.assertEqual(_audit(d)[-1]["action"], "screen_capture")


class AgentR3ToolTests(unittest.TestCase):
    def test_mcp_call_halts_for_r3_then_confirm_runs_exact_call(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            hub = api._hub
            fake_tools = [{"name": "mcp_demo_add", "server": "demo", "tool": "add",
                           "decl": {"name": "mcp_demo_add", "description": "x",
                                    "parameters": {"type": "object", "properties": {}}}}]
            seen = {}

            def turn(system, contents, decls, key, timeout=45.0):
                seen["decls"] = [x["name"] for x in decls]
                return _fn_call("mcp_demo_add", {"a": 2, "b": 40, "confirmed": True})

            with mock.patch("mcp_client.list_tools", lambda root: fake_tools), \
                 mock.patch.object(worker, "_gemini_turn", turn):
                hub.start("coding", "add")
                _wait_standby(hub, "coding")
            self.assertIn("mcp_demo_add", seen["decls"])
            row = next(a for a in hub.list() if a["id"] == "coding")
            self.assertTrue(row["detail"].startswith("needs_r3_tool:"))
            self.assertFalse(row["detail"].startswith("needs_r3:"))
            tok = row["pending"]["token"]
            # Wrong token / shell path cannot execute it.
            self.assertFalse(api.tool_confirm("coding", "nope")["ok"])
            self.assertFalse(api.shell_confirm("MCP demo.add", "coding")["ok"])
            calls = []
            with mock.patch("mcp_client.call_tool",
                            lambda root, s, t, a: calls.append((s, t, a)) or {"ok": True, "data": {"text": "42"}}):
                r = api.tool_confirm("coding", tok)
            self.assertTrue(r["ok"])
            self.assertEqual(calls, [("demo", "add", {"a": 2, "b": 40, "confirmed": True})])
            self.assertIsNone(hub.pending("coding"))
            self.assertIn("mcp_call", [a["action"] for a in _audit(d)])
            # Token is single-use.
            self.assertFalse(api.tool_confirm("coding", tok)["ok"])

    def test_screen_read_from_agent_needs_r3(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            hub = api._hub
            with mock.patch("mcp_client.list_tools", lambda root: []), \
                 mock.patch.object(worker, "_gemini_turn",
                                   lambda *a, **k: _fn_call("screen_read", {"question": "what app?"})):
                hub.start("system", "look")
                _wait_standby(hub, "system")
            p = hub.pending("system")
            self.assertEqual(p["kind"], "screen")
            self.assertTrue(api.tool_reject("system")["ok"])
            self.assertIsNone(hub.pending("system"))

    def test_memory_role_gets_no_mcp(self):
        with tempfile.TemporaryDirectory() as d:
            hub = AgentHub(root=Path(d), gemini_key="k")
            seen = {}

            def turn(system, contents, decls, key, timeout=45.0):
                seen["decls"] = [x["name"] for x in decls]
                return {"candidates": [{"content": {"parts": [{"text": "done"}]}}]}

            with mock.patch("mcp_client.list_tools", lambda root: [{"name": "mcp_x_y", "server": "x", "tool": "y",
                                                                     "decl": {"name": "mcp_x_y"}}]), \
                 mock.patch.object(worker, "_gemini_turn", turn):
                hub.start("memory", "x")
                _wait_standby(hub, "memory")
            self.assertNotIn("mcp_x_y", seen["decls"])


if __name__ == "__main__":
    unittest.main()
