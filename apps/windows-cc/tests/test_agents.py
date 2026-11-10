import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

from agents.registry import ROLES
from agents.worker import AgentHub


class TestAgents(unittest.TestCase):
    def test_roles_six_plus_builder(self):
        self.assertEqual(
            {r["id"] for r in ROLES},
            {"coding", "research", "memory", "browser", "task", "system", "builder", "video"},
        )

    def test_start_stop_standby(self):
        with tempfile.TemporaryDirectory() as td:
            hub = AgentHub(root=Path(td), gemini_key="")
            self.assertTrue(all(a["state"] == "standby" for a in hub.list()))
            hub.start("system")
            time.sleep(0.3)
            hub.stop("system")
            self.assertEqual(
                next(a for a in hub.list() if a["id"] == "system")["state"], "standby"
            )

    def test_start_without_gemini_key_sets_error(self):
        with tempfile.TemporaryDirectory() as td:
            hub = AgentHub(root=Path(td), gemini_key="")
            hub.start("research", goal="fetch example")
            for _ in range(20):
                row = next(a for a in hub.list() if a["id"] == "research")
                if row["state"] != "active":
                    break
                time.sleep(0.05)
            row = next(a for a in hub.list() if a["id"] == "research")
            self.assertEqual(row["state"], "error")
            self.assertIn("missing_key", row.get("detail") or "")

    def test_tool_schemas_include_new_tools(self):
        from agent_tools import TOOL_SCHEMAS
        names = {t["name"] for t in TOOL_SCHEMAS}
        for n in ("code_search", "shell", "memory_note"):
            self.assertIn(n, names)

    def test_role_declarations_filtered(self):
        from agents.worker import MAX_STEPS, _declarations_for
        self.assertEqual(MAX_STEPS, 12)
        coding = next(r for r in ROLES if r["id"] == "coding")
        self.assertIn("shell", coding["tools"])
        self.assertIn("code_search", coding["tools"])
        decl = {d["name"] for d in _declarations_for(set(coding["tools"]))}
        self.assertEqual(decl, set(coding["tools"]))
        mem = next(r for r in ROLES if r["id"] == "memory")
        self.assertIn("memory_note", mem["tools"])

    def test_needs_r3_halts_loop(self):
        from unittest import mock
        import agents.worker as w
        raw = {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "shell", "args": {"command": "rm -rf x"}}}]}}]}
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(w, "_gemini_turn", return_value=raw), \
             mock.patch.object(w.AgentTools, "call",
                               return_value={"ok": False, "needs_r3": True, "command": "rm -rf x"}):
            hub = AgentHub(root=Path(td), gemini_key="k")
            hub._goals["system"] = "x"
            hub._run("system")
            row = next(a for a in hub.list() if a["id"] == "system")
            self.assertEqual(row["state"], "standby")
            self.assertTrue(row["detail"].startswith("needs_r3:rm -rf x"))

    def test_fallback_json_protocol(self):
        from unittest import mock
        import agents.worker as w
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(w, "_gemini_turn", side_effect=w.ToolsRejected("400")), \
             mock.patch.object(w, "_gemini_json", return_value='{"final":"ok"}'):
            hub = AgentHub(root=Path(td), gemini_key="k")
            hub._run("coding")
            row = next(a for a in hub.list() if a["id"] == "coding")
            self.assertIn("fallback_json_protocol", row["steps"])
            self.assertEqual(row["last_reply"], "ok")


if __name__ == "__main__":
    unittest.main()
