# apps/windows-room/tests/test_room_bridge.py
"""Room reuses windows-cc BridgeApi. No second bridge, no fabricated tiles."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROOM = ROOT / "apps" / "windows-room"
sys.path.insert(0, str(ROOM))
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))
sys.path.insert(0, str(ROOT / "apps" / "windows-panel"))
sys.path.insert(0, str(ROOT / "scripts" / "win"))

import room_api


def _make_root(tmp: Path, *, approved: bool = True) -> Path:
    (tmp / "STATE.md").write_text("# STATE\n", encoding="utf-8")
    status = "approved" if approved else "draft"
    (tmp / "POLICY.yaml").write_text(
        f"status: {status}\nschedule:\n  quiet_hours: \"00:00-00:00\"\n",
        encoding="utf-8",
    )
    (tmp / "reports").mkdir(exist_ok=True)
    (tmp / "logs").mkdir(exist_ok=True)
    return tmp


class TestRoomUsesCommandCenterBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = _make_root(Path(self.tmp.name))
        self.api = room_api.make_api(root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_class_is_windows_cc_bridge(self):
        BridgeApi = room_api.load_bridge_class()
        self.assertIsInstance(self.api, BridgeApi)
        import bridge_api

        self.assertEqual(
            Path(bridge_api.__file__).resolve(),
            (ROOT / "apps" / "windows-cc" / "bridge_api.py").resolve(),
        )
        self.assertFalse((ROOM / "bridge_api.py").exists())

    def test_required_surface(self):
        for name in room_api.REQUIRED_METHODS:
            self.assertTrue(callable(getattr(self.api, name)), name)

    def test_status_from_policy_file(self):
        out = self.api.status()
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"]["system_status"], "SYSTEMS NOMINAL")
        self.assertTrue(out["data"]["policy_ok"])
        self.assertEqual(out["data"]["root"], str(self.root.resolve()))

    def test_status_policy_not_approved(self):
        root = _make_root(Path(tempfile.mkdtemp()), approved=False)
        api = room_api.make_api(root=root)
        self.assertEqual(api.status()["data"]["system_status"], "POLICY NOT APPROVED")

    def test_feed_is_disk_audit_only(self):
        empty = self.api.feed(10)
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["data"]["items"], [])
        line = {"task": "room-test", "action": "ping", "result": "ok"}
        (self.root / "logs" / "audit.jsonl").write_text(
            json.dumps(line) + "\n", encoding="utf-8"
        )
        got = self.api.feed(10)
        self.assertEqual(got["data"]["items"], [line])

    def test_memory_counts_real_files(self):
        out = self.api.memory()
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["data"]["nodes"], 1)
        self.assertIn("STATE.md", out["data"]["sources"])

    def test_skills_empty_then_one_directory(self):
        self.assertEqual(self.api.skills()["data"]["skills"], [])
        skill = self.root / "skills" / "demo-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Demo\nReads a file.\n", encoding="utf-8")
        rows = self.api.skills()["data"]["skills"]
        self.assertEqual([r["name"] for r in rows], ["demo-skill"])
        self.assertIn("Reads a file.", rows[0]["summary"])

    def test_metrics_are_host_readings(self):
        out = self.api.metrics()
        self.assertTrue(out["ok"], out)
        data = out["data"]
        self.assertTrue({"cpu_pct", "ram_pct", "disk_pct"} <= set(data))
        for key in ("cpu_pct", "ram_pct", "disk_pct"):
            self.assertGreaterEqual(data[key], 0.0)
            self.assertLessEqual(data[key], 100.0)

    def test_workday_blocked_without_r3(self):
        out = self.api.start_workday(False)
        self.assertFalse(out["ok"])
        self.assertIn("R3", out["error"])

    def test_agents_match_registry_standby(self):
        out = self.api.agents()
        self.assertTrue(out["ok"])
        ids = [a["id"] for a in out["data"]["agents"]]
        self.assertEqual(
            ids,
            ["coding", "research", "memory", "browser", "task", "system"],
        )
        self.assertTrue(all(a["state"] == "standby" for a in out["data"]["agents"]))

    def test_brief_reads_today_file(self):
        day = self.api.status()["data"]["today"]
        self.assertEqual(self.api.brief()["data"]["text"], "")
        (self.root / "reports" / f"{day}.md").write_text("# Brief\nHello room\n", encoding="utf-8")
        self.assertIn("Hello room", self.api.brief()["data"]["text"])


if __name__ == "__main__":
    unittest.main()
