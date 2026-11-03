import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOM = Path(__file__).resolve().parents[1]


def _load_host():
    spec = importlib.util.spec_from_file_location("room_host_main", ROOM / "host_main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # sets sys.path; no webview import at module level
    return mod


class TestRoomBridgeImport(unittest.TestCase):
    def test_bridge_status_via_room_paths(self):
        host = _load_host()
        self.assertTrue(callable(host.discover_root))
        from bridge_api import BridgeApi

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "STATE.md").write_text("# STATE\n", encoding="utf-8")
            (root / "POLICY.yaml").write_text(
                'status: approved\nschedule:\n  quiet_hours: "00:00-00:00"\n', encoding="utf-8"
            )
            (root / "reports").mkdir()
            (root / "logs").mkdir()
            out = BridgeApi(root=root).status()
            self.assertTrue(out["ok"], out)
            self.assertIn("system_status", out["data"])
            self.assertFalse(BridgeApi(root=root).start_workday(False)["ok"])

    def test_discover_root_env(self):
        host = _load_host()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "STATE.md").write_text("x", encoding="utf-8")
            (root / "POLICY.yaml").write_text("status: approved\n", encoding="utf-8")
            import os
            os.environ["JARVIS_HOME"] = str(root)
            try:
                self.assertEqual(host.discover_root(), root.resolve())
            finally:
                os.environ.pop("JARVIS_HOME", None)


if __name__ == "__main__":
    unittest.main()
