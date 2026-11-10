import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

from agent_tools import AgentTools, TOOL_SCHEMAS  # noqa: E402


class BuilderToolTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.t = AgentTools(self.root, actor="agent-builder")

    def tearDown(self):
        self.td.cleanup()

    def test_schemas_present(self):
        names = {s["name"] for s in TOOL_SCHEMAS}
        for n in ("write_file", "make_dir", "delete_file", "ws_list_dir", "ws_read_file"):
            self.assertIn(n, names)

    def test_write_new_file_inside_workspace(self):
        r = self.t.call("write_file", {"path": "test-site/index.html", "content": "<h1>Hi</h1>"})
        self.assertTrue(r["ok"], r)
        p = self.root / "workspace" / "test-site" / "index.html"
        self.assertEqual(p.read_text(encoding="utf-8"), "<h1>Hi</h1>")
        self.assertTrue(r["data"]["created"])
        audit = (self.root / "logs" / "audit.jsonl").read_text(encoding="utf-8")
        self.assertIn("agent_write_file", audit)
        self.assertNotIn("<h1>", audit)

    def test_traversal_and_absolute_blocked(self):
        for bad in ("../x.txt", "test-site/../../x.txt", "/etc/passwd", "C:/Windows/x.txt",
                    "C:x.txt", "\\\\server\\share\\x", "test-site/a:stream", "test-site/CON.txt"):
            r = self.t.call("write_file", {"path": bad, "content": "x"})
            self.assertFalse(r["ok"], bad)
            self.assertFalse(r.get("needs_r3"), bad)
        self.assertFalse((self.root / "x.txt").exists())

    def test_file_directly_in_workspace_root_blocked(self):
        r = self.t.call("write_file", {"path": "__init__.py", "content": ""})
        self.assertFalse(r["ok"])

    def test_size_limit_and_blocked_ext(self):
        big = "a" * (512_001)
        self.assertFalse(self.t.call("write_file", {"path": "p/big.txt", "content": big})["ok"])
        self.assertFalse(self.t.call("write_file", {"path": "p/x.exe", "content": "MZ"})["ok"])

    def test_overwrite_needs_r3_until_confirmed(self):
        self.t.call("write_file", {"path": "p/a.txt", "content": "one"})
        r = self.t.call("write_file", {"path": "p/a.txt", "content": "two", "confirmed": True})
        self.assertTrue(r.get("needs_r3"))
        self.assertEqual(r["kind"], "file")
        self.assertEqual(r["op"], "overwrite")
        self.assertEqual((self.root / "workspace/p/a.txt").read_text(), "one")
        r2 = self.t.write_file("p/a.txt", "two", confirmed=True)
        self.assertTrue(r2["ok"])
        self.assertEqual((self.root / "workspace/p/a.txt").read_text(), "two")

    def test_delete_needs_r3(self):
        self.t.call("write_file", {"path": "p/a.txt", "content": "one"})
        r = self.t.call("delete_file", {"path": "p/a.txt"})
        self.assertTrue(r.get("needs_r3"))
        self.assertTrue((self.root / "workspace/p/a.txt").exists())
        self.assertTrue(self.t.delete_file("p/a.txt", confirmed=True)["ok"])
        self.assertFalse((self.root / "workspace/p/a.txt").exists())

    def test_make_dir_list_read(self):
        self.assertTrue(self.t.call("make_dir", {"path": "p/src"})["ok"])
        self.t.call("write_file", {"path": "p/src/m.py", "content": "print(1)"})
        ls = self.t.call("ws_list_dir", {"path": "p"})
        self.assertIn("src", [e["name"] for e in ls["data"]["entries"]])
        self.assertEqual(self.t.call("ws_read_file", {"path": "p/src/m.py"})["data"]["text"], "print(1)")
        top = self.t.call("ws_list_dir", {})
        self.assertTrue(top["ok"])

    def test_workspace_python_is_never_auto(self):
        self.t.call("make_dir", {"path": "p"})
        r = self.t.call("shell", {"cmd": "python -m unittest", "cwd": "p"})
        self.assertTrue(r.get("needs_r3"))
        self.assertEqual(r.get("cwd"), "p")
        r = self.t.call("shell", {"cmd": "python -m unittest workspace/p/test_x.py"})
        self.assertTrue(r.get("needs_r3"))

    def test_shell_dir_in_workspace_ok(self):
        self.t.call("make_dir", {"path": "p"})
        r = self.t.call("shell", {"cmd": "dir", "cwd": "p"})
        self.assertFalse(r.get("needs_r3"))

    def test_shell_cwd_outside_rejected(self):
        r = self.t.call("shell", {"cmd": "dir", "cwd": "../.."})
        self.assertFalse(r["ok"])
        self.assertFalse(r.get("needs_r3"))


if __name__ == "__main__":
    unittest.main()
