import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

from agent_tools import AgentTools


class TestAgentTools(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("hi", encoding="utf-8")
            tools = AgentTools(root)
            with self.assertRaises(ValueError):
                tools.safe_path("../outside.txt")
            with self.assertRaises(ValueError):
                tools.safe_path(str(Path(td).parent / "x"))

    def test_read_file_ok(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("hello", encoding="utf-8")
            r = AgentTools(root).read_file("ok.txt")
            self.assertTrue(r["ok"])
            self.assertEqual(r["data"]["text"], "hello")

    def test_web_fetch_rejects_non_http(self):
        with tempfile.TemporaryDirectory() as td:
            r = AgentTools(Path(td)).web_fetch("file:///etc/passwd")
            self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
