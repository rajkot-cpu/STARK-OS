# apps/windows-cc/agent_tools.py
from __future__ import annotations

import subprocess
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
import urllib.request
from pathlib import Path

from shell_gate import is_allowlisted, normalize

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "vendor", "dist", "build", ".worktrees"}
_BIN_EXT = {".exe", ".dll", ".pyd", ".so", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".pdf", ".bin", ".pyc", ".woff", ".woff2"}
_IST = timezone(timedelta(hours=5, minutes=30))

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
    {
        "name": "code_search",
        "description": "Case-insensitive text search across files under JARVIS root",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_hits": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_note",
        "description": "Append a timestamped note to memory/agent_notes.md",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "shell",
        "description": "Run an allowlisted shell command (git status, git log -n N, python -m unittest, dir/ls); others need R3 confirmation",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "required": ["cmd"],
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

    def code_search(self, query: str, max_hits: int = 20) -> dict:
        q = (query or "").lower()
        if not q:
            return {"ok": False, "error": "empty query"}
        max_hits = max(1, min(int(max_hits or 20), 200))
        hits = []
        try:
            for p in sorted(self.root.rglob("*")):
                if len(hits) >= max_hits:
                    break
                rel = p.relative_to(self.root)
                if any(part in _SKIP_DIRS for part in rel.parts):
                    continue
                if not p.is_file() or p.suffix.lower() in _BIN_EXT:
                    continue
                try:
                    if p.stat().st_size > 1_000_000:
                        continue
                    raw = p.read_bytes()
                except OSError:
                    continue
                if b"\0" in raw[:4096]:
                    continue
                for i, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
                    if q in line.lower():
                        hits.append({"path": rel.as_posix(), "line": i, "text": line.strip()[:300]})
                        if len(hits) >= max_hits:
                            break
            return {"ok": True, "data": {"query": query, "hits": hits, "truncated": len(hits) >= max_hits}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def memory_note(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty note"}
        try:
            p = self.safe_path("memory/agent_notes.md")
            p.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(_IST).isoformat(timespec="seconds")
            with p.open("a", encoding="utf-8") as f:
                f.write(f"- [{ts}] {text}\n")
            return {"ok": True, "data": {"path": str(p), "timestamp": ts}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def shell(self, cmd: str, confirmed: bool = False) -> dict:
        if not is_allowlisted(cmd) and not confirmed:
            return {"ok": False, "needs_r3": True, "command": cmd}
        c = normalize(cmd)
        if c.lower().startswith("python ") and is_allowlisted(cmd):
            c = f'"{sys.executable}"' + c[len("python"):]
        try:
            r = subprocess.run(
                c, shell=True, cwd=str(self.root), timeout=30,
                capture_output=True, text=True,
            )
            return {
                "ok": r.returncode == 0,
                "data": {
                    "command": cmd,
                    "returncode": r.returncode,
                    "stdout": r.stdout[-20_000:],
                    "stderr": r.stderr[-20_000:],
                },
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout after 30s", "command": cmd}
        except Exception as e:
            return {"ok": False, "error": str(e), "command": cmd}

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
        if name == "code_search":
            return self.code_search(args["query"], args.get("max_hits") or 20)
        if name == "memory_note":
            return self.memory_note(args["text"])
        if name == "shell":
            return self.shell(args["cmd"], bool(args.get("confirmed", False)))
        return {"ok": False, "error": f"unknown tool {name}"}
