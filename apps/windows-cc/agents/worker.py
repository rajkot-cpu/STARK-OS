# apps/windows-cc/agents/worker.py
from __future__ import annotations

import json
import threading
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from agent_tools import TOOL_SCHEMAS, AgentTools
from llm_providers import _resolve_key, load_secrets

from .registry import ROLES

MAX_STEPS = 12
MODEL = "gemini-3.1-flash-lite-preview"


def _role(role_id: str) -> dict | None:
    for r in ROLES:
        if r["id"] == role_id:
            return r
    return None


def _gemini_json(system: str, user: str, key: str, timeout: float = 45.0) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={key}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": 800, "temperature": 0.3},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"Gemini HTTP {e.code}: {err}") from e
    parts = (raw.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    text = " ".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned empty reply")
    return text


def _parse_action(text: str) -> dict:
    """Expect JSON: {\"final\": \"...\"} or {\"tool\": \"name\", \"args\": {...}}."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(cleaned[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {"final": cleaned[:800]}


def _gemini_turn(
    system: str,
    contents: list,
    declarations: list,
    key: str,
    timeout: float = 45.0,
) -> dict:
    """One native function-calling turn; returns raw API JSON."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={key}"
    )
    body: dict = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 800, "temperature": 0.3},
    }
    if declarations:
        body["tools"] = [{"functionDeclarations": declarations}]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:200]
        if e.code == 400:
            raise ToolsRejected(f"Gemini HTTP {e.code}: {err}") from e
        raise RuntimeError(f"Gemini HTTP {e.code}: {err}") from e


class ToolsRejected(RuntimeError):
    """API rejected the request (HTTP 400) — likely tools unsupported."""


def _declarations_for(allowed: set[str]) -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in TOOL_SCHEMAS
        if t["name"] in allowed
    ]


def _candidate_parts(raw: dict) -> tuple[dict, list]:
    content = (raw.get("candidates") or [{}])[0].get("content") or {}
    return content, content.get("parts") or []


class AgentHub:
    def __init__(self, root: Path, gemini_key: str | None = None):
        self.root = Path(root)
        self._gemini_key_override = gemini_key
        self._state = {r["id"]: "standby" for r in ROLES}
        self._threads: dict[str, threading.Thread] = {}
        self._stop = {r["id"]: threading.Event() for r in ROLES}
        self._detail = {r["id"]: "" for r in ROLES}
        self._last_reply = {r["id"]: "" for r in ROLES}
        self._steps = {r["id"]: [] for r in ROLES}
        self._goals = {r["id"]: "" for r in ROLES}
        # Pending R3 tool requests (MCP / screen) awaiting operator confirm.
        self._pending: dict[str, dict] = {}
        self._mcp_maps: dict[str, dict] = {r["id"]: {} for r in ROLES}

    def pending(self, role_id: str) -> dict | None:
        p = self._pending.get(role_id)
        return dict(p) if p else None

    def take_pending(self, role_id: str, token: str) -> dict | None:
        """Pop the pending R3 tool request iff the token matches."""
        p = self._pending.get(role_id)
        if not p or not token or p.get("token") != token:
            return None
        self._pending.pop(role_id, None)
        if str(self._detail.get(role_id, "")).startswith("needs_r3_tool:"):
            self._detail[role_id] = "tool confirmed"
        self._steps[role_id] = [s for s in self._steps[role_id] if not s.startswith("needs_r3_tool:")]
        return p

    def reject_pending(self, role_id: str) -> bool:
        if self._pending.pop(role_id, None) is None:
            return False
        self._detail[role_id] = "tool rejected"
        self._steps[role_id] = [s for s in self._steps[role_id] if not s.startswith("needs_r3_tool:")]
        return True

    def record_result(self, role_id: str, text: str) -> None:
        if role_id in self._last_reply:
            self._last_reply[role_id] = str(text)[:2000]

    def clear_r3(self, role_id: str) -> bool:
        """Clear a pending needs_r3 detail after the user confirmed the shell command."""
        if str(self._detail.get(role_id, "")).startswith("needs_r3:"):
            self._detail[role_id] = "shell confirmed"
            self._steps[role_id] = [s for s in self._steps[role_id] if not s.startswith("needs_r3:")]
            return True
        return False

    def list(self) -> list[dict]:
        out = []
        for r in ROLES:
            rid = r["id"]
            out.append(
                {
                    "id": rid,
                    "name": r["name"],
                    "state": self._state[rid],
                    "detail": self._detail[rid],
                    "last_reply": self._last_reply[rid],
                    "steps": list(self._steps[rid]),
                    "tools": r["tools"],
                    "pending": _pending_view(self._pending.get(rid)),
                }
            )
        return out

    def start(self, role_id: str, goal: str | None = None) -> dict:
        if role_id not in self._state:
            return {"ok": False, "error": "unknown role"}
        if self._state[role_id] == "active":
            return {"ok": True, "data": {"id": role_id, "state": "active"}}
        self._stop[role_id].clear()
        self._goals[role_id] = (goal or "").strip()
        self._steps[role_id] = []
        self._last_reply[role_id] = ""
        self._pending.pop(role_id, None)
        self._detail[role_id] = "starting"
        self._state[role_id] = "active"
        t = threading.Thread(target=self._run, args=(role_id,), daemon=True)
        self._threads[role_id] = t
        t.start()
        return {"ok": True, "data": {"id": role_id, "state": "active"}}

    def stop(self, role_id: str) -> dict:
        if role_id not in self._state:
            return {"ok": False, "error": "unknown role"}
        self._stop[role_id].set()
        self._state[role_id] = "standby"
        if not self._detail[role_id]:
            self._detail[role_id] = "stopped"
        return {"ok": True, "data": {"id": role_id, "state": "standby"}}

    def _resolve_gemini(self) -> str:
        if self._gemini_key_override is not None:
            return self._gemini_key_override.strip()
        load_secrets(self.root)
        return _resolve_key(
            "JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")
        )

    def _run(self, role_id: str) -> None:
        role = _role(role_id)
        if not role:
            self._state[role_id] = "error"
            self._detail[role_id] = "unknown role"
            return
        key = self._resolve_gemini()
        if not key:
            self._state[role_id] = "error"
            self._detail[role_id] = "missing_key"
            self._last_reply[role_id] = "missing_key"
            return

        tools = AgentTools(self.root)
        allowed = set(role["tools"])
        declarations = _declarations_for(allowed)
        self._mcp_maps[role_id] = {}
        if role.get("mcp"):
            try:
                from mcp_client import list_tools

                for t in list_tools(self.root):
                    if t["name"] in allowed:
                        continue
                    self._mcp_maps[role_id][t["name"]] = t
                    allowed.add(t["name"])
                    declarations.append(t["decl"])
                if self._mcp_maps[role_id]:
                    self._steps[role_id].append(f"mcp tools: {len(self._mcp_maps[role_id])}")
            except Exception as e:
                self._steps[role_id].append(f"mcp unavailable: {type(e).__name__}")
        goal = self._goals[role_id] or (
            "Give a short status using available tools if helpful."
        )
        system = (
            f"{role['prompt']}\n"
            "Call tools when useful, then answer the operator in plain text."
        )
        contents: list = [{"role": "user", "parts": [{"text": f"Goal: {goal}"}]}]
        try:
            for step_i in range(MAX_STEPS):
                if self._stop[role_id].is_set():
                    self._detail[role_id] = "stopped"
                    self._state[role_id] = "standby"
                    return
                self._detail[role_id] = f"step {step_i + 1}/{MAX_STEPS}"
                try:
                    raw = _gemini_turn(system, contents, declarations, key)
                except ToolsRejected:
                    self._steps[role_id].append("fallback_json_protocol")
                    self._run_json(role_id, role, tools, allowed, goal, key, step_i)
                    return
                content, parts = _candidate_parts(raw)
                calls = [p["functionCall"] for p in parts if "functionCall" in p]
                if not calls:
                    text = " ".join(p.get("text", "") for p in parts).strip()
                    if not text:
                        raise RuntimeError("Gemini returned empty reply")
                    self._last_reply[role_id] = text[:2000]
                    self._steps[role_id].append("final")
                    self._detail[role_id] = "done"
                    self._state[role_id] = "standby"
                    return
                contents.append({"role": "model", "parts": parts})
                responses = []
                for call in calls:
                    name = str(call.get("name") or "")
                    args = call.get("args") if isinstance(call.get("args"), dict) else {}
                    result = self._exec_tool(role_id, tools, allowed, name, args)
                    if isinstance(result, dict) and result.get("needs_r3"):
                        self._halt_r3(role_id, result)
                        return
                    responses.append(
                        {"functionResponse": {"name": name, "response": _wrap(result)}}
                    )
                contents.append({"role": "user", "parts": responses})
            self._finish_max(role_id)
        except Exception as e:
            self._state[role_id] = "error"
            self._detail[role_id] = str(e)[:200]
            self._last_reply[role_id] = f"error: {e}"[:500]

    def _exec_tool(self, role_id, tools, allowed, name, args):
        if name not in allowed:
            msg = f"blocked tool {name}"
            self._steps[role_id].append(msg)
            return {"ok": False, "error": msg}
        self._steps[role_id].append(
            f"{name}({json.dumps(args, ensure_ascii=False)[:120]})"
        )
        mcp = self._mcp_maps.get(role_id, {}).get(name)
        if mcp:
            # Every MCP tool call is R3; the model can never mark it confirmed.
            return {"ok": False, "needs_r3": True, "kind": "mcp", "server": mcp["server"],
                    "tool": mcp["tool"], "args": dict(args or {})}
        return tools.call(name, args)

    def _halt_r3(self, role_id: str, result: dict) -> None:
        kind = result.get("kind")
        if kind in ("mcp", "screen"):
            token = uuid.uuid4().hex[:12]
            if kind == "mcp":
                label = f"MCP {result.get('server')}.{result.get('tool')}"
                pend = {"kind": "mcp", "server": str(result.get("server")), "tool": str(result.get("tool")),
                        "args": result.get("args") or {}, "token": token, "label": label}
            else:
                label = "Screen capture"
                pend = {"kind": "screen", "question": str(result.get("question") or ""),
                        "token": token, "label": label}
            self._pending[role_id] = pend
            self._steps[role_id].append(f"needs_r3_tool: {label}"[:160])
            self._detail[role_id] = "needs_r3_tool:" + label
            self._last_reply[role_id] = f"{label} needs operator R3 approval."
            self._state[role_id] = "standby"
            return
        cmd = str(result.get("command") or "")
        self._steps[role_id].append(f"needs_r3: {cmd[:120]}")
        self._detail[role_id] = "needs_r3:" + cmd
        self._last_reply[role_id] = (
            f"Shell command needs operator R3 approval: {cmd}"[:2000]
        )
        self._state[role_id] = "standby"

    def _finish_max(self, role_id: str) -> None:
        self._last_reply[role_id] = (
            self._last_reply[role_id] or "Reached max steps without a final answer."
        )
        self._detail[role_id] = "max_steps"
        self._state[role_id] = "standby"

    def _run_json(self, role_id, role, tools, allowed, goal, key, used: int) -> None:
        """One-shot fallback: legacy JSON-text protocol (no native tools)."""
        system = (
            f"{role['prompt']}\n"
            f"Allowed tools: {', '.join(sorted(allowed))}.\n"
            "Reply with ONLY JSON, one of:\n"
            '  {"tool":"<name>","args":{...}}\n'
            '  {"final":"<your answer to the operator>"}\n'
            "No markdown fences."
        )
        transcript = f"Goal: {goal}\n"
        for step_i in range(used, MAX_STEPS):
            if self._stop[role_id].is_set():
                self._detail[role_id] = "stopped"
                self._state[role_id] = "standby"
                return
            self._detail[role_id] = f"step {step_i + 1}/{MAX_STEPS}"
            action = _parse_action(_gemini_json(system, transcript, key))
            if action.get("final") is not None:
                self._last_reply[role_id] = str(action["final"]).strip()[:2000]
                self._steps[role_id].append("final")
                self._detail[role_id] = "done"
                self._state[role_id] = "standby"
                return
            name = str(action.get("tool") or "")
            args = action.get("args") if isinstance(action.get("args"), dict) else {}
            result = self._exec_tool(role_id, tools, allowed, name, args)
            if isinstance(result, dict) and result.get("needs_r3"):
                self._halt_r3(role_id, result)
                return
            transcript += (
                f"Tool {name} args={json.dumps(args)}\n"
                f"Result: {json.dumps(result)[:4000]}\n"
            )
        self._finish_max(role_id)


def _pending_view(p: dict | None) -> dict | None:
    if not p:
        return None
    out = {"kind": p.get("kind"), "label": p.get("label"), "token": p.get("token")}
    if p.get("kind") == "mcp":
        out["args_preview"] = json.dumps(p.get("args") or {}, ensure_ascii=False)[:400]
    else:
        out["question"] = str(p.get("question") or "")[:300]
    return out


def _wrap(result) -> dict:
    """functionResponse.response must be a JSON object."""
    dumped = json.dumps(result, default=str)
    if len(dumped) > 8000:
        return {"truncated": dumped[:8000]}
    if isinstance(result, dict):
        return json.loads(dumped)
    return {"result": result}
