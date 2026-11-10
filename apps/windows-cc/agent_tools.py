# apps/windows-cc/agent_tools.py
from __future__ import annotations

import os
import re
import shlex
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
            },
            "required": ["cmd"],
        },
    },
]


TOOL_SCHEMAS += [
    {
        "name": "web_search",
        "description": "Search the public web (read-only). Returns titles, URLs and snippets to summarize; cite URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "screen_read",
        "description": "Ask the operator to let Jarvis capture and describe the current screen once. Needs operator R3 approval every time.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": [],
        },
    },
]


TOOL_SCHEMAS += [
    {
        "name": "ws_list_dir",
        "description": "List a folder inside the build workspace (jarvis/workspace). Path like 'my-app' or 'my-app/src'; empty = list projects.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []},
    },
    {
        "name": "ws_read_file",
        "description": "Read a text file inside the build workspace, e.g. 'my-app/index.html'.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "write_file",
        "description": (
            "Create a NEW text file inside the build workspace. path = '<project>/<file>', e.g. "
            "'test-site/index.html' (folders are created). Overwriting an existing file needs operator R3 approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "make_dir",
        "description": "Create a folder inside the build workspace, e.g. 'my-app/src'.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "delete_file",
        "description": "Delete a file inside the build workspace. Always needs operator R3 approval.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
]
for _s in TOOL_SCHEMAS:
    if _s["name"] == "shell":
        _s["parameters"]["properties"]["cwd"] = {
            "type": "string",
            "description": "Optional workspace project folder to run in, e.g. 'test-site'",
        }

WS_MAX_FILE = 512_000
WS_MAX_PROJECT = 20_000_000
_WS_BLOCK_EXT = {".exe", ".dll", ".scr", ".msi", ".lnk", ".sys", ".com", ".pif", ".cpl", ".url"}
_WIN_RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


class AgentTools:
    def __init__(self, root: Path, actor: str = "agent"):
        self.root = Path(root).resolve()
        self.actor = actor or "agent"

    # ---- build workspace (jarvis/workspace/<project>/...) ----

    @property
    def ws_root(self) -> Path:
        return self.root / "workspace"

    def ws_path(self, rel: str, *, allow_root: bool = False) -> Path:
        """Resolve a workspace-relative path; raise ValueError if it escapes."""
        raw = str(rel or "").strip().replace("\\", "/")
        if not raw or raw in (".", "./"):
            if allow_root:
                return self.ws_root
            raise ValueError("path required (e.g. 'my-app/index.html')")
        if raw.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", raw) or ":" in raw:
            raise ValueError("absolute paths/drive letters are not allowed; use '<project>/<file>'")
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise ValueError("'..' is not allowed")
        for p in parts:
            if p.split(".")[0].lower() in _WIN_RESERVED or p.endswith((" ", ".")):
                raise ValueError(f"invalid name: {p}")
        ws = self.ws_root.resolve() if self.ws_root.exists() else self.ws_root
        target = (self.ws_root / "/".join(parts)).resolve()
        if target != ws and ws not in target.parents:
            raise ValueError("path outside workspace")
        if not allow_root and target == ws:
            raise ValueError("path must be inside a project folder")
        return target

    def _ws_rel(self, p: Path) -> str:
        try:
            return p.relative_to(self.ws_root.resolve()).as_posix()
        except ValueError:
            return p.name

    def _audit(self, action: str, result: str, undo: str = "") -> None:
        try:
            from cc_settings import audit

            audit(self.root, self.actor, action, result, undo)
        except Exception:
            pass

    def ws_list_dir(self, path: str = "") -> dict:
        try:
            self.ws_root.mkdir(parents=True, exist_ok=True)
            d = self.ws_path(path, allow_root=True)
            if not d.is_dir():
                return {"ok": False, "error": "not a directory"}
            entries = [
                {"name": c.name, "is_dir": c.is_dir(), "bytes": (c.stat().st_size if c.is_file() else None)}
                for c in sorted(d.iterdir())[:300]
            ]
            return {"ok": True, "data": {"path": self._ws_rel(d) or ".", "entries": entries}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def ws_read_file(self, path: str, max_bytes: int = 100_000) -> dict:
        try:
            p = self.ws_path(path)
            if not p.is_file():
                return {"ok": False, "error": "not a file"}
            return {"ok": True, "data": {"path": self._ws_rel(p),
                                         "text": p.read_bytes()[:max_bytes].decode("utf-8", errors="replace")}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def make_dir(self, path: str) -> dict:
        try:
            p = self.ws_path(path)
            if p.exists() and not p.is_dir():
                return {"ok": False, "error": "a file with that name exists"}
            p.mkdir(parents=True, exist_ok=True)
            self._audit("agent_make_dir", f"workspace/{self._ws_rel(p)}")
            return {"ok": True, "data": {"path": self._ws_rel(p)}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _project_bytes(self, p: Path) -> int:
        try:
            proj = self.ws_root.resolve() / p.relative_to(self.ws_root.resolve()).parts[0]
            return sum(f.stat().st_size for f in proj.rglob("*") if f.is_file())
        except Exception:
            return 0

    def write_file(self, path: str, content: str, confirmed: bool = False) -> dict:
        try:
            p = self.ws_path(path)
            rel = self._ws_rel(p)
            if "/" not in rel:
                return {"ok": False, "error": "put files inside a project folder: '<project>/<file>'"}
            if p.suffix.lower() in _WS_BLOCK_EXT:
                return {"ok": False, "error": f"file type {p.suffix} is not allowed"}
            data = str(content if content is not None else "").encode("utf-8")
            if len(data) > WS_MAX_FILE:
                return {"ok": False, "error": f"file too large ({len(data)} bytes > {WS_MAX_FILE})"}
            if p.is_dir():
                return {"ok": False, "error": "a folder with that name exists"}
            exists = p.exists()
            if exists and not confirmed:
                return {"ok": False, "needs_r3": True, "kind": "file", "op": "overwrite",
                        "path": rel, "content": str(content or ""), "bytes": len(data)}
            if self._project_bytes(p) + len(data) > WS_MAX_PROJECT:
                return {"ok": False, "error": "project size limit reached (20 MB)"}
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            self._audit("agent_write_file" if not exists else "agent_overwrite_file",
                        f"workspace/{rel} ({len(data)} B){' R3 confirmed' if exists else ''}",
                        f"delete workspace/{rel}" if not exists else "previous content not kept")
            return {"ok": True, "data": {"path": rel, "abs_path": str(p), "bytes": len(data), "created": not exists}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_file(self, path: str, confirmed: bool = False) -> dict:
        try:
            p = self.ws_path(path)
            rel = self._ws_rel(p)
            if not p.exists():
                return {"ok": False, "error": "not found"}
            if p.is_dir() and any(p.iterdir()):
                return {"ok": False, "error": "folder not empty"}
            if not confirmed:
                return {"ok": False, "needs_r3": True, "kind": "file", "op": "delete", "path": rel}
            if p.is_dir():
                p.rmdir()
            else:
                p.unlink()
            self._audit("agent_delete_file", f"workspace/{rel} (R3 confirmed)", "not recoverable")
            return {"ok": True, "data": {"path": rel, "deleted": True}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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

    def web_search(self, query: str, max_results: int = 5) -> dict:
        try:
            from llm_providers import _resolve_key, load_secrets
            from web_search import search

            load_secrets(self.root)
            key = _resolve_key("JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY"))
            return search(query, max_results=max_results, gemini_key=key)
        except Exception as e:
            return {"ok": False, "error": f"web_search: {type(e).__name__}"}

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

    def shell(self, cmd: str, confirmed: bool = False, cwd: str = "") -> dict:
        run_dir = self.root
        cwd = str(cwd or "").strip()
        if cwd:
            try:
                run_dir = self.ws_path(cwd)
            except ValueError as e:
                return {"ok": False, "error": f"cwd: {e}"}
            if not run_dir.is_dir():
                return {"ok": False, "error": "cwd: project folder does not exist"}
        c = normalize(cmd)
        allow = is_allowlisted(cmd)
        if allow and (cwd or "workspace" in c.lower()) and c.split(" ", 1)[0].lower() != "dir" \
                and c.split(" ", 1)[0].lower() != "ls":
            # Agent-written code in the workspace never runs without operator approval.
            allow = False
        if not allow and not confirmed:
            out = {"ok": False, "needs_r3": True, "command": cmd}
            if cwd:
                out["cwd"] = cwd
            return out
        head = c.split(" ", 1)[0].lower()
        try:
            if allow and head == "ls" and os.name == "nt":
                # `ls` does not exist on Windows; map to the `dir` builtin.
                rest = c[2:].strip()
                c = ("dir " + rest).strip()
                head = "dir"
            if allow and head != "dir":
                # Allowlisted commands run without a shell (no expansion).
                args = shlex.split(c)
                if args and args[0].lower() == "python":
                    args[0] = sys.executable
                run_target, use_shell = args, False
            else:
                # `dir` is a cmd builtin; confirmed commands run as typed (R3).
                run_target, use_shell = c, True
            r = subprocess.run(
                run_target, shell=use_shell, cwd=str(run_dir), timeout=60,
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
            return {"ok": False, "error": "timeout after 60s", "command": cmd}
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
        if name == "web_search":
            return self.web_search(args.get("query") or "", args.get("max_results") or 5)
        if name == "screen_read":
            # Every capture is R3: only BridgeApi.tool_confirm may run it.
            return {"ok": False, "needs_r3": True, "kind": "screen",
                    "question": str(args.get("question") or "")[:300]}
        if name == "shell":
            # Never honour model-supplied `confirmed`; only BridgeApi.shell_confirm may.
            return self.shell(args.get("cmd") or args.get("command") or "", confirmed=False,
                              cwd=str(args.get("cwd") or ""))
        if name == "ws_list_dir":
            return self.ws_list_dir(args.get("path") or "")
        if name == "ws_read_file":
            return self.ws_read_file(args.get("path") or "")
        if name == "write_file":
            # Never honour model-supplied `confirmed`; overwrite is R3 via BridgeApi.tool_confirm.
            return self.write_file(args.get("path") or "", args.get("content") or "", confirmed=False)
        if name == "make_dir":
            return self.make_dir(args.get("path") or "")
        if name == "delete_file":
            return self.delete_file(args.get("path") or "", confirmed=False)
        return {"ok": False, "error": f"unknown tool {name}"}
