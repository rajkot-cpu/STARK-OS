import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import mcp_client  # noqa: E402

ALLOWED = mcp_client._ALLOWED


def _walk(s):
    yield s
    for v in (s.get("properties") or {}).values():
        yield from _walk(v)
    if isinstance(s.get("items"), dict):
        yield from _walk(s["items"])


def _cfg(root: Path, servers):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "mcp_servers.json").write_text(json.dumps({"servers": servers}))


class SanitizeTests(unittest.TestCase):
    def test_strips_unsupported_keys(self):
        raw = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "addArguments", "type": "object", "additionalProperties": False,
            "properties": {
                "a": {"title": "A", "type": "integer", "default": 1},
                "path": {"type": ["string", "null"], "pattern": "^/", "minLength": 1},
                "mode": {"anyOf": [{"type": "string", "enum": ["r", "w"]}, {"type": "null"}]},
                "tags": {"type": "array", "items": {"type": "string", "$ref": "#/x"}},
                "when": {"type": "string", "format": "uri"},
            },
            "required": ["a", "ghost"],
            "$defs": {"x": {}},
        }
        out = mcp_client.sanitize_schema(raw)
        for node in _walk(out):
            self.assertTrue(set(node) <= ALLOWED, node)
        self.assertEqual(out["required"], ["a"])
        self.assertEqual(out["properties"]["path"], {"type": "string", "nullable": True})
        self.assertEqual(out["properties"]["mode"]["enum"], ["r", "w"])
        self.assertTrue(out["properties"]["mode"]["nullable"])
        self.assertNotIn("format", out["properties"]["when"])

    def test_decl_name_is_gemini_safe(self):
        n = mcp_client.decl_name("files", "read-file.v2" + "x" * 80)
        self.assertTrue(n.startswith("mcp_files_"))
        self.assertLessEqual(len(n), 64)
        self.assertRegex(n, r"^[A-Za-z0-9_]+$")


class ConfigTests(unittest.TestCase):
    def test_missing_and_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(mcp_client.load_servers(d), ([], ""))
            self.assertEqual(mcp_client.list_tools(d), [])
            _cfg(Path(d), [])
            self.assertEqual(mcp_client.load_servers(d)[0], [])

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            (Path(d) / "config" / "mcp_servers.json").write_text("{nope")
            servers, err = mcp_client.load_servers(d)
            self.assertEqual(servers, [])
            self.assertIn("invalid", err)

    def test_public_view_hides_env_values(self):
        with tempfile.TemporaryDirectory() as d:
            _cfg(Path(d), [{"name": "x", "command": "py", "env": {"TOKEN": "s3cret"}}])
            view = json.dumps(mcp_client.public_view(d))
            self.assertNotIn("s3cret", view)
            self.assertIn("TOKEN", view)

    def test_disabled_server_not_listed(self):
        with tempfile.TemporaryDirectory() as d:
            _cfg(Path(d), [{"name": "x", "command": "py", "enabled": False}])
            self.assertEqual(mcp_client.list_tools(d, lister=lambda s: 1 / 0), [])

    def test_shipped_default_is_empty(self):
        cfg = json.loads((ROOT / "config" / "mcp_servers.json").read_text())
        self.assertEqual(cfg["servers"], [])
        ex = json.loads((ROOT / "config" / "mcp_servers.example.json").read_text())
        self.assertTrue(all(s.get("enabled") is False for s in ex["servers"]))


class LiveStdioTests(unittest.TestCase):
    def test_list_and_call_demo_server(self):
        try:
            import mcp  # noqa: F401
        except Exception:
            self.skipTest("mcp not installed")
        server = str(Path(__file__).parent / "fixtures" / "mcp_demo_server.py")
        with tempfile.TemporaryDirectory() as d:
            _cfg(Path(d), [{"name": "demo", "command": sys.executable, "args": [server]}])
            tools = mcp_client.list_tools(d, force=True)
            names = {t["tool"] for t in tools}
            self.assertIn("add", names)
            add = next(t for t in tools if t["tool"] == "add")
            self.assertEqual(add["name"], "mcp_demo_add")
            self.assertEqual(set(add["decl"]["parameters"]["properties"]), {"a", "b"})
            r = mcp_client.call_tool(d, "demo", "add", {"a": 2, "b": 40})
            self.assertTrue(r["ok"], r)
            self.assertIn("42", r["data"]["text"])
            self.assertFalse(mcp_client.call_tool(d, "ghost", "add", {})["ok"])


if __name__ == "__main__":
    unittest.main()
