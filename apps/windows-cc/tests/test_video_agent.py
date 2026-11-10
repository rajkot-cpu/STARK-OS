import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.worker import AgentHub  # noqa: E402
from test_video_pipeline import SCRIPT, make_deps  # noqa: E402


class VideoAgentTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.events = []
        self.hub = AgentHub(self.root, gemini_key="fake-key", on_event=lambda r, k, row: self.events.append(k))

    def tearDown(self):
        self.td.cleanup()

    def _factory(self, replies):
        def f(root, providers, progress=None, on_provider=None):
            self.providers = providers
            if on_provider:
                on_provider("gemini")
            d, _ = make_deps(list(replies))
            return d
        return f

    def test_video_agent_runs_pipeline_and_reports(self):
        self.hub.video_deps = self._factory([json.dumps(SCRIPT)])
        self.assertTrue(self.hub.start("video", "make a short on chess")["ok"])
        row = self.hub.wait("video", 30)
        self.assertEqual(row["state"], "standby", row)
        self.assertEqual(row["detail"], "done")
        self.assertTrue(row["folder"].startswith(str(self.root / "workspace" / "videos")))
        self.assertTrue(any(f.endswith("video.mp4") for f in row["files"]))
        self.assertIn("Video ready", row["last_reply"])
        self.assertIn("Not uploaded", row["last_reply"])
        self.assertEqual(row["provider"], "gemini")
        self.assertEqual(self.providers, [("gemini", "fake-key")])
        self.assertIn("progress", self.events)
        self.assertEqual(self.events[-1], "done")

    def test_empty_goal_defaults_to_trend_video(self):
        self.hub.video_deps = self._factory([json.dumps({"index": 1, "topic": "India vs NZ"}), json.dumps(SCRIPT)])
        self.hub.start("video", "")
        row = self.hub.wait("video", 30)
        self.assertEqual(row["detail"], "done", row)
        self.assertIn("trend", row["goal"].lower())

    def test_video_agent_error_is_reported(self):
        self.hub.video_deps = self._factory(["nope", "still nope"])
        self.hub.start("video", "make a short on chess")
        row = self.hub.wait("video", 30)
        self.assertEqual(row["state"], "error")
        self.assertIn("video failed", row["detail"])
        self.assertEqual(self.events[-1], "error")


class BridgeOpenFolderTests(unittest.TestCase):
    def test_refuses_outside_workspace(self):
        import bridge_api

        with tempfile.TemporaryDirectory() as td:
            b = bridge_api.BridgeApi.__new__(bridge_api.BridgeApi)
            b.root = Path(td)
            (Path(td) / "workspace").mkdir()
            self.assertFalse(b.open_folder(td)["ok"])
            self.assertFalse(b.open_folder(str(Path(td) / "workspace" / ".." / ".."))["ok"])


if __name__ == "__main__":
    unittest.main()
