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
    def test_six_roles(self):
        self.assertEqual(
            {r["id"] for r in ROLES},
            {"coding", "research", "memory", "browser", "task", "system"},
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


if __name__ == "__main__":
    unittest.main()
