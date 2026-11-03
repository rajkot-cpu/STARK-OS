# apps/windows-cc/tests/test_bridge_shell_confirm.py
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in ("apps/windows-cc", "apps/windows-panel", "scripts/win"):
    sys.path.insert(0, str(ROOT / p))


class ShellConfirmTests(unittest.TestCase):
    def test_bridge_has_shell_confirm(self):
        from bridge_api import BridgeApi
        self.assertTrue(callable(getattr(BridgeApi, "shell_confirm", None)))

    def test_unconfirmed_needs_r3(self):
        from agent_tools import AgentTools
        with tempfile.TemporaryDirectory() as d:
            r = AgentTools(Path(d)).shell("echo hi > x.txt")
            self.assertTrue(r.get("needs_r3"))
            self.assertEqual(r.get("command"), "echo hi > x.txt")

    def test_empty_command_rejected(self):
        from bridge_api import BridgeApi
        api = BridgeApi.__new__(BridgeApi)
        api.root = Path(tempfile.gettempdir())
        self.assertFalse(api.shell_confirm("")["ok"])

    def test_confirm_clears_r3_detail(self):
        from bridge_api import BridgeApi
        from agents.worker import AgentHub, ROLES
        rid = ROLES[0]["id"]
        with tempfile.TemporaryDirectory() as d:
            api = BridgeApi.__new__(BridgeApi)
            api.root = Path(d)
            api._hub = AgentHub(root=Path(d))
            api._hub._detail[rid] = "needs_r3:echo hi > x.txt"
            api._hub._steps[rid].append("needs_r3: echo hi > x.txt")
            r = api.shell_confirm("echo hi > x.txt", rid)
            self.assertTrue(r.get("ok"), r)
            self.assertFalse(api._hub._detail[rid].startswith("needs_r3:"))
            self.assertFalse(any(s.startswith("needs_r3:") for s in api._hub._steps[rid]))

    def test_confirm_mismatch_rejected(self):
        from bridge_api import BridgeApi
        from agents.worker import AgentHub, ROLES
        rid = ROLES[0]["id"]
        with tempfile.TemporaryDirectory() as d:
            api = BridgeApi.__new__(BridgeApi)
            api.root = Path(d)
            api._hub = AgentHub(root=Path(d))
            api._hub._detail[rid] = "needs_r3:echo hi > x.txt"
            r = api.shell_confirm("echo pwned > y.txt", rid)
            self.assertFalse(r.get("ok"))
            self.assertFalse((Path(d) / "y.txt").exists())
            self.assertTrue(api._hub._detail[rid].startswith("needs_r3:"))

    def test_confirm_requires_role_and_pending(self):
        from bridge_api import BridgeApi
        from agents.worker import AgentHub, ROLES
        with tempfile.TemporaryDirectory() as d:
            api = BridgeApi.__new__(BridgeApi)
            api.root = Path(d)
            api._hub = AgentHub(root=Path(d))
            self.assertFalse(api.shell_confirm("echo hi > x.txt")["ok"])
            self.assertFalse(api.shell_confirm("echo hi > x.txt", ROLES[0]["id"])["ok"])
            self.assertFalse((Path(d) / "x.txt").exists())


if __name__ == "__main__":
    unittest.main()
