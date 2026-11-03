# apps/windows-cc/agent_tools.py
from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

TOOL_SCHEMAS = [
    {
        "name": "list_dir",
        "description": "List files under JARVIS root",
        "parameters": {
            "type": "object",
            "properties": {"rel": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file under JARVIS root",
        "parameters": {
            "type": "object",
            "properties": {"rel": {"type": "string"}},
            "required": ["rel"],
        },
    },
    {
        "name": "web_fetch",
        "description": "HTTP GET a public URL",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "skills_list",
        "description": "List skill folder names",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "skill_run",
        "description": "Preview a skill SKILL.md (read-only)",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


class AgentTools:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def safe_path(self, rel_or_abs: str) -> Path:
        raw = Path(rel_or_abs)
        p = (self.root / rel_or_abs).resolve() if not raw.is_absolute() else raw.resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"path outside jarvis root: {rel_or_abs}")
        return p

    def list_dir(self, rel: str = ".") -> dict:
        try:
            d = self.safe_path(rel)
            if not d.is_dir():
                return {"ok": False, "error": "not a directory"}
            entries = [
                {"name": c.name, "is_dir": c.is_dir()}
                for c in sorted(d.iterdir())[:200]
            ]
            return {"ok": True, "data": {"entries": entries}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def read_file(self, rel: str, max_bytes: int = 100_000) -> dict:
        try:
            p = self.safe_path(rel)
            if not p.is_file():
                return {"ok": False, "error": "not a file"}
            data = p.read_bytes()[:max_bytes]
            return {
                "ok": True,
                "data": {
                    "path": str(p),
                    "text": data.decode("utf-8", errors="replace"),
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def web_fetch(self, url: str, max_bytes: int = 200_000, timeout: float = 15.0) -> dict:
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"ok": False, "error": "only http(s) allowed"}
        try:
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": "JARVIS-Agent/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            text = raw[:max_bytes].decode("utf-8", errors="replace")
            return {
                "ok": True,
                "data": {"url": url, "text": text, "truncated": truncated},
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def skills_list(self) -> dict:
        skills = self.root / "skills"
        if not skills.is_dir():
            return {"ok": True, "data": {"skills": []}}
        names = sorted(
            [
                p.name
                for p in skills.iterdir()
                if p.is_dir() and (p / "SKILL.md").exists()
            ]
        )
        return {"ok": True, "data": {"skills": names}}

    def skill_run(self, name: str) -> dict:
        if "/" in name or "\\" in name or ".." in name:
            return {"ok": False, "error": "invalid skill name"}
        p = self.root / "skills" / name / "SKILL.md"
        try:
            self.safe_path(str(p))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if not p.is_file():
            return {"ok": False, "error": "skill not found"}
        preview = p.read_text(encoding="utf-8", errors="replace")[:500]
        return {
            "ok": True,
            "data": {"name": name, "path": str(p), "preview": preview},
        }

    def call(self, name: str, args: dict) -> dict:
        args = args or {}
        if name == "list_dir":
            return self.list_dir(args.get("rel") or ".")
        if name == "read_file":
            return self.read_file(args["rel"])
        if name == "web_fetch":
            return self.web_fetch(args["url"])
        if name == "skills_list":
            return self.skills_list()
        if name == "skill_run":
            return self.skill_run(args["name"])
        return {"ok": False, "error": f"unknown tool {name}"}
