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

    def test_code_search_finds_line(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("hello_unique_xyz = 1\n", encoding="utf-8")
            r = AgentTools(root).code_search("hello_unique_xyz")
            self.assertTrue(r["ok"])
            self.assertTrue(any("hello_unique_xyz" in h["text"] for h in r["data"]["hits"]))

    def test_shell_needs_r3(self):
        with tempfile.TemporaryDirectory() as td:
            r = AgentTools(Path(td)).shell("echo pwn")
            self.assertTrue(r.get("needs_r3"))
            self.assertFalse(r["ok"])
            self.assertEqual(r["command"], "echo pwn")

    def test_memory_note_appends(self):
        with tempfile.TemporaryDirectory() as td:
            t = AgentTools(Path(td))
            self.assertTrue(t.memory_note("first")["ok"])
            t.call("memory_note", {"text": "second"})
            body = (Path(td) / "memory" / "agent_notes.md").read_text(encoding="utf-8")
            self.assertIn("first", body)
            self.assertIn("second", body)



class ShellHardeningTests(unittest.TestCase):
    def test_model_cannot_self_confirm(self):
        from agent_tools import AgentTools, TOOL_SCHEMAS
        sh = [t for t in TOOL_SCHEMAS if t["name"] == "shell"][0]
        self.assertNotIn("confirmed", sh["parameters"]["properties"])
        with tempfile.TemporaryDirectory() as d:
            r = AgentTools(Path(d)).call("shell", {"cmd": "echo x > z.txt", "confirmed": True})
            self.assertTrue(r.get("needs_r3"), r)
            self.assertFalse((Path(d) / "z.txt").exists())

    def test_quotes_rejected_by_gate(self):
        from shell_gate import is_allowlisted
        self.assertFalse(is_allowlisted('dir "a b'))
        self.assertFalse(is_allowlisted("python -m unittest 'x"))


if __name__ == "__main__":
    unittest.main()
