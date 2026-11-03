# apps/windows-cc/agents/worker.py
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from agent_tools import TOOL_SCHEMAS, AgentTools
from llm_providers import _resolve_key, load_secrets

from .registry import ROLES

MAX_STEPS = 8
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
        tool_help = ", ".join(sorted(allowed))
        system = (
            f"{role['prompt']}\n"
            f"Allowed tools: {tool_help}.\n"
            "Reply with ONLY JSON, one of:\n"
            '  {"tool":"<name>","args":{...}}\n'
            '  {"final":"<your answer to the operator>"}\n'
            "No markdown fences."
        )
        goal = self._goals[role_id] or (
            "Give a short status using available tools if helpful."
        )
        transcript = f"Goal: {goal}\n"
        try:
            for step_i in range(MAX_STEPS):
                if self._stop[role_id].is_set():
                    self._detail[role_id] = "stopped"
                    self._state[role_id] = "standby"
                    return
                self._detail[role_id] = f"step {step_i + 1}/{MAX_STEPS}"
                raw = _gemini_json(system, transcript, key)
                action = _parse_action(raw)
                if "final" in action and action.get("final") is not None:
                    reply = str(action.get("final") or "").strip()
                    self._last_reply[role_id] = reply[:2000]
                    self._steps[role_id].append("final")
                    self._detail[role_id] = "done"
                    self._state[role_id] = "standby"
                    return
                tool_name = str(action.get("tool") or "")
                args = action.get("args") if isinstance(action.get("args"), dict) else {}
                if tool_name not in allowed:
                    msg = f"blocked tool {tool_name}"
                    self._steps[role_id].append(msg)
                    transcript += f"Assistant tried invalid tool. Result: {msg}\n"
                    continue
                result = tools.call(tool_name, args)
                step_line = f"{tool_name}({json.dumps(args, ensure_ascii=False)[:120]})"
                self._steps[role_id].append(step_line)
                transcript += (
                    f"Tool {tool_name} args={json.dumps(args)}\n"
                    f"Result: {json.dumps(result)[:4000]}\n"
                )
            self._last_reply[role_id] = (
                self._last_reply[role_id]
                or "Reached max steps without a final answer."
            )
            self._detail[role_id] = "max_steps"
            self._state[role_id] = "standby"
        except Exception as e:
            self._state[role_id] = "error"
            self._detail[role_id] = str(e)[:200]
            self._last_reply[role_id] = f"error: {e}"[:500]
