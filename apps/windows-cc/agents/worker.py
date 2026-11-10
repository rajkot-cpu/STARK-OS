# apps/windows-cc/agents/worker.py
from __future__ import annotations

import json
import threading
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from agent_tools import TOOL_SCHEMAS, AgentTools
from llm_providers import USER_AGENT, _resolve_key, groq_extra, groq_model, load_secrets  # UA: Groq/Cloudflare 403s Python-urllib

from .registry import ROLES

MAX_STEPS = 12
MODEL = "gemini-3.1-flash-lite-preview"
OPENAI_MODEL = "gpt-4o-mini"
MAX_OUT_TOKENS = 4096
PROVIDER_LABEL = {"gemini": "Gemini", "openai": "OpenAI", "groq": "Groq"}


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
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
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
        "generationConfig": {"maxOutputTokens": MAX_OUT_TOKENS, "temperature": 0.3},
    }
    if declarations:
        body["tools"] = [{"functionDeclarations": declarations}]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:3000]
        if e.code == 400:
            raise ToolsRejected(f"Gemini HTTP {e.code}: {err[:300]}") from e
        raise ProviderUnavailable("gemini", e.code, err) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderUnavailable("gemini", None, type(e).__name__) from e


class ToolsRejected(RuntimeError):
    """API rejected the request (HTTP 400) — likely tools unsupported."""


class ProviderUnavailable(RuntimeError):
    """Provider can't serve this turn (quota, outage, auth, network) — try the next one."""

    def __init__(self, provider: str, code: int | None, body: str = ""):
        self.provider = provider
        self.code = code
        self.reason = _reason(provider, code, body)
        self.retry_after = _retry_after(body)
        super().__init__(self.reason)


class AllProvidersFailed(RuntimeError):
    pass


def _retry_after(body: str) -> float | None:
    import re

    m = re.search(r'"retryDelay"\s*:\s*"([0-9.]+)s"', body or "")
    return float(m.group(1)) if m else None


RETRIES = 2          # per provider, for 429 rate limits and 5xx before falling back
RETRY_CAP = 30.0     # seconds


def _sleep(sec: float) -> None:
    import time

    time.sleep(sec)


def _reason(provider: str, code: int | None, body: str) -> str:
    label = PROVIDER_LABEL.get(provider, provider)
    b = (body or "").lower()
    if code == 429:
        if "insufficient_quota" in b or "credit" in b:
            return f"{label} out of credits (429)"
        return f"{label} quota exceeded (429)"
    if code in (401, 403):
        return f"{label} key rejected ({code})"
    if code == 404:
        return f"{label} model not found (404)"
    if code is not None and code >= 500:
        return f"{label} server error ({code})"
    if code is None:
        return f"{label} unreachable ({body or 'network'})"
    return f"{label} HTTP {code}"


def _openai_turn(system: str, messages: list, tools: list, key: str, *,
                 provider: str = "openai", timeout: float = 60.0) -> dict:
    """One chat.completions tool-calling turn (OpenAI or an OpenAI-compatible API)."""
    if provider == "groq":
        url, model = "https://api.groq.com/openai/v1/chat/completions", groq_model()
    else:
        url, model = "https://api.openai.com/v1/chat/completions", OPENAI_MODEL
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": MAX_OUT_TOKENS,
        "temperature": 0.3,
    }
    if provider == "groq":
        body.update(groq_extra(model))
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                 "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:3000]
        raise ProviderUnavailable(provider, e.code, err) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ProviderUnavailable(provider, None, type(e).__name__) from e


# ---- provider-neutral history -------------------------------------------------
# {"role":"user","text":...}
# {"role":"assistant","text":...,"calls":[{"id","name","args"}],"gemini_parts":[...]|None}
# {"role":"tool","results":[{"id","name","result"}]}


def _to_gemini(history: list) -> list:
    out = []
    for h in history:
        if h["role"] == "user":
            out.append({"role": "user", "parts": [{"text": h["text"]}]})
        elif h["role"] == "assistant":
            parts = h.get("gemini_parts")
            if not parts:
                parts = ([{"text": h["text"]}] if h.get("text") else []) + [
                    {"functionCall": {"name": c["name"], "args": c["args"]}} for c in h["calls"]
                ]
            out.append({"role": "model", "parts": parts})
        else:
            out.append({"role": "user", "parts": [
                {"functionResponse": {"name": r["name"], "response": _wrap(r["result"])}}
                for r in h["results"]
            ]})
    return out


def _to_openai(history: list) -> list:
    out = []
    for h in history:
        if h["role"] == "user":
            out.append({"role": "user", "content": h["text"]})
        elif h["role"] == "assistant":
            msg: dict = {"role": "assistant", "content": h.get("text") or None}
            if h["calls"]:
                msg["tool_calls"] = [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}}
                    for c in h["calls"]
                ]
            out.append(msg)
        else:
            for r in h["results"]:
                out.append({"role": "tool", "tool_call_id": r["id"],
                            "content": json.dumps(_wrap(r["result"]), ensure_ascii=False)[:8000]})
    return out


def _openai_tools(declarations: list) -> list:
    return [{"type": "function", "function": {
        "name": d["name"], "description": d.get("description", ""),
        "parameters": d.get("parameters") or {"type": "object", "properties": {}},
    }} for d in declarations]


def _gemini_step(system, history, declarations, key) -> dict:
    raw = _gemini_turn(system, _to_gemini(history), declarations, key)
    _content, parts = _candidate_parts(raw)
    calls = []
    for i, p in enumerate(parts):
        if "functionCall" in p:
            fc = p["functionCall"]
            calls.append({"id": str(fc.get("id") or f"g{uuid.uuid4().hex[:8]}_{i}"),
                          "name": str(fc.get("name") or ""),
                          "args": fc.get("args") if isinstance(fc.get("args"), dict) else {}})
    text = " ".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought")).strip()
    return {"text": text, "calls": calls, "gemini_parts": parts}


def _openai_step(system, history, declarations, key, provider="openai") -> dict:
    raw = _openai_turn(system, _to_openai(history), _openai_tools(declarations), key, provider=provider)
    msg = (raw.get("choices") or [{}])[0].get("message") or {}
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": str(tc.get("id") or uuid.uuid4().hex[:8]),
                      "name": str(fn.get("name") or ""),
                      "args": args if isinstance(args, dict) else {}})
    return {"text": (msg.get("content") or "").strip(), "calls": calls, "gemini_parts": None}


def _declarations_for(allowed: set[str]) -> list[dict]:
    return [
        {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
        for t in TOOL_SCHEMAS
        if t["name"] in allowed
    ]


def _candidate_parts(raw: dict) -> tuple[dict, list]:
    content = (raw.get("candidates") or [{}])[0].get("content") or {}
    return content, content.get("parts") or []



_KEY_ENV = {
    "gemini": ("JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    "openai": ("JARVIS_OPENAI_API_KEY", ("OPENAI_API_KEY",)),
    "groq": ("JARVIS_GROQ_API_KEY", ("GROQ_API_KEY",)),
}
PROVIDER_ORDER = ("gemini", "openai", "groq")


class AgentHub:
    def __init__(self, root: Path, gemini_key: str | None = None, keys: dict | None = None,
                 on_event=None):
        self.root = Path(root)
        self._gemini_key_override = gemini_key
        self._key_overrides = dict(keys or {})
        self.on_event = on_event
        self._lock = threading.RLock()
        self._state = {r["id"]: "standby" for r in ROLES}
        self._threads: dict[str, threading.Thread] = {}
        self._stop = {r["id"]: threading.Event() for r in ROLES}
        self._detail = {r["id"]: "" for r in ROLES}
        self._last_reply = {r["id"]: "" for r in ROLES}
        self._steps = {r["id"]: [] for r in ROLES}
        self._goals = {r["id"]: "" for r in ROLES}
        self._provider = {r["id"]: "" for r in ROLES}
        self._notice = {r["id"]: "" for r in ROLES}
        self._files = {r["id"]: [] for r in ROLES}
        # Pending R3 tool requests (MCP / screen / file) awaiting operator confirm.
        self._pending: dict[str, dict] = {}
        self._pending_shell_cwd: dict[str, str] = {}
        # Saved loop state while an R3 request waits, so the agent resumes after approval.
        self._halted: dict[str, dict] = {}
        self._mcp_maps: dict[str, dict] = {r["id"]: {} for r in ROLES}
        self._folder = {r["id"]: "" for r in ROLES}
        # Tests inject a fake: callable(root, providers, progress, on_provider) -> video_studio Deps.
        self.video_deps = None

    # ---- R3 plumbing ----

    def pending(self, role_id: str) -> dict | None:
        p = self._pending.get(role_id)
        return dict(p) if p else None

    def pending_shell_cwd(self, role_id: str) -> str:
        return self._pending_shell_cwd.get(role_id, "")

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
        self.resume(role_id, {"ok": False, "error": "operator rejected this action"})
        return True

    def record_result(self, role_id: str, text: str) -> None:
        if role_id in self._last_reply:
            self._last_reply[role_id] = str(text)[:2000]

    def note_file(self, role_id: str, rel: str) -> None:
        if role_id in self._files and rel and rel not in self._files[role_id]:
            self._files[role_id].append(rel)

    def clear_r3(self, role_id: str) -> bool:
        """Clear a pending needs_r3 detail after the user confirmed the shell command."""
        if str(self._detail.get(role_id, "")).startswith("needs_r3:"):
            self._detail[role_id] = "shell confirmed"
            self._steps[role_id] = [s for s in self._steps[role_id] if not s.startswith("needs_r3:")]
            self._pending_shell_cwd.pop(role_id, None)
            return True
        return False

    def resume(self, role_id: str, result) -> bool:
        """Feed the operator-approved (or rejected) tool result back and continue the run."""
        with self._lock:
            saved = self._halted.pop(role_id, None)
            if not saved or self._state.get(role_id) == "active":
                return False
            call = saved["call"]
            results = saved["done"] + [{"id": call["id"], "name": call["name"], "result": result}] + [
                {"id": c["id"], "name": c["name"],
                 "result": {"ok": False, "error": "skipped while waiting for operator approval; call again if still needed"}}
                for c in saved["skipped"]
            ]
            saved["history"].append({"role": "tool", "results": results})
            self._steps[role_id].append("resumed after operator decision")
            self._stop[role_id].clear()
            self._state[role_id] = "active"
            self._detail[role_id] = "resuming"
            t = threading.Thread(target=self._run, args=(role_id, saved), daemon=True)
            self._threads[role_id] = t
            t.start()
            return True

    # ---- views / lifecycle ----

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
                    "goal": self._goals[rid],
                    "provider": self._provider[rid],
                    "notice": self._notice[rid],
                    "files": list(self._files[rid]),
                    "workspace": str(self.root / "workspace") if ("write_file" in r["tools"] or r.get("pipeline")) else "",
                    "folder": self._folder[rid],
                }
            )
        return out

    def start(self, role_id: str, goal: str | None = None) -> dict:
        with self._lock:
            if role_id not in self._state:
                return {"ok": False, "error": "unknown role"}
            if self._state[role_id] == "active":
                return {"ok": False, "error": f"{_role(role_id)['name']} is busy: {self._goals[role_id][:80]}",
                        "busy": True, "data": {"id": role_id, "state": "active"}}
            self._stop[role_id].clear()
            self._goals[role_id] = (goal or "").strip()
            self._steps[role_id] = []
            self._last_reply[role_id] = ""
            self._pending.pop(role_id, None)
            self._halted.pop(role_id, None)
            self._pending_shell_cwd.pop(role_id, None)
            self._files[role_id] = []
            self._folder[role_id] = ""
            self._notice[role_id] = ""
            self._provider[role_id] = ""
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
        self._halted.pop(role_id, None)
        self._state[role_id] = "standby"
        if not self._detail[role_id]:
            self._detail[role_id] = "stopped"
        return {"ok": True, "data": {"id": role_id, "state": "standby"}}

    def wait(self, role_id: str, timeout: float = 300.0) -> dict:
        """Block until the role is no longer active (headless tests / scripts)."""
        import time

        t0 = time.time()
        while self._state.get(role_id) == "active" and time.time() - t0 < timeout:
            time.sleep(0.2)
        return next(a for a in self.list() if a["id"] == role_id)

    def _emit(self, role_id: str, kind: str) -> None:
        cb = self.on_event
        if not cb:
            return
        try:
            cb(role_id, kind, next(a for a in self.list() if a["id"] == role_id))
        except Exception:
            pass

    # ---- providers ----

    def _resolve_gemini(self) -> str:
        if self._gemini_key_override is not None:
            return self._gemini_key_override.strip()
        load_secrets(self.root)
        return _resolve_key(*_KEY_ENV["gemini"])

    def _providers(self) -> list[tuple[str, str]]:
        out = []
        for name in PROVIDER_ORDER:
            if name == "gemini":
                key = self._resolve_gemini()
            elif name in self._key_overrides:
                key = (self._key_overrides[name] or "").strip()
            elif self._gemini_key_override is not None and not self._key_overrides:
                key = ""  # explicit test/override mode: Gemini only
            else:
                load_secrets(self.root)
                key = _resolve_key(*_KEY_ENV[name])
            if key:
                out.append((name, key))
        return out

    def _llm_turn(self, role_id, providers, idx, system, history, declarations):
        notes = []
        attempt = 0
        while idx < len(providers):
            name, key = providers[idx]
            try:
                if name == "gemini":
                    turn = _gemini_step(system, history, declarations, key)
                else:
                    turn = _openai_step(system, history, declarations, key, provider=name)
                if self._provider[role_id] != name:
                    self._provider[role_id] = name
                    self._steps[role_id].append(f"provider: {PROVIDER_LABEL.get(name, name)}")
                return turn, idx
            except ProviderUnavailable as e:
                transient = e.code == 429 or (e.code is not None and e.code >= 500)
                out_of_credit = "out of credits" in e.reason
                if transient and not out_of_credit and attempt < RETRIES and not self._stop[role_id].is_set():
                    attempt += 1
                    wait = min(e.retry_after or 5.0 * attempt, RETRY_CAP)
                    self._steps[role_id].append(f"{e.reason} — retrying in {int(wait)}s")
                    self._detail[role_id] = f"waiting {int(wait)}s ({e.reason})"
                    _sleep(wait)
                    continue
                attempt = 0
                notes.append(e.reason)
                idx += 1
                if idx < len(providers):
                    nxt = PROVIDER_LABEL.get(providers[idx][0], providers[idx][0])
                    msg = f"{e.reason} — using {nxt}"
                else:
                    msg = e.reason
                self._notice[role_id] = msg
                self._steps[role_id].append("⚠ " + msg)
        raise AllProvidersFailed("All AI providers failed: " + "; ".join(notes))

    # ---- main loop ----

    def _run(self, role_id: str, saved: dict | None = None) -> None:
        role = _role(role_id)
        if not role:
            self._state[role_id] = "error"
            self._detail[role_id] = "unknown role"
            return
        providers = self._providers()
        if not providers:
            self._state[role_id] = "error"
            self._detail[role_id] = "missing_key"
            self._last_reply[role_id] = "missing_key — add a Gemini or OpenAI key on the API Keys / secrets file"
            self._emit(role_id, "error")
            return

        if role.get("pipeline") == "video":
            self._run_video(role_id, providers)
            return

        tools = AgentTools(self.root, actor=f"agent-{role_id}")
        allowed = set(role["tools"])
        declarations = _declarations_for(allowed)
        if saved is None:
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
                if self._mcp_maps[role_id] and saved is None:
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
        max_steps = int(role.get("max_steps") or MAX_STEPS)
        if saved:
            history, idx, first = saved["history"], saved["idx"], saved["step"]
        else:
            history, idx, first = [{"role": "user", "text": f"Goal: {goal}"}], 0, 0
        try:
            for step_i in range(first, max_steps):
                if self._stop[role_id].is_set():
                    self._detail[role_id] = "stopped"
                    self._state[role_id] = "standby"
                    return
                self._detail[role_id] = f"step {step_i + 1}/{max_steps}"
                try:
                    turn, idx = self._llm_turn(role_id, providers, idx, system, history, declarations)
                except ToolsRejected:
                    self._steps[role_id].append("fallback_json_protocol")
                    self._run_json(role_id, role, tools, allowed, goal, providers[idx][1], step_i)
                    det = str(self._detail[role_id])
                    self._emit(role_id, "error" if self._state[role_id] == "error"
                               else ("needs_approval" if det.startswith("needs_r3") else "done"))
                    return
                if not turn["calls"]:
                    text = turn["text"]
                    if not text:
                        raise RuntimeError(f"{PROVIDER_LABEL.get(providers[idx][0])} returned empty reply")
                    self._last_reply[role_id] = text[:2000]
                    self._steps[role_id].append("final")
                    self._detail[role_id] = "done"
                    self._state[role_id] = "standby"
                    self._emit(role_id, "done")
                    return
                history.append({"role": "assistant", "text": turn["text"], "calls": turn["calls"],
                                "gemini_parts": turn["gemini_parts"]})
                done = []
                for i, call in enumerate(turn["calls"]):
                    if self._stop[role_id].is_set():
                        break
                    result = self._exec_tool(role_id, tools, allowed, call["name"], call["args"])
                    if isinstance(result, dict) and result.get("needs_r3"):
                        self._halted[role_id] = {
                            "history": history, "idx": idx, "step": step_i + 1,
                            "done": done, "call": call, "skipped": turn["calls"][i + 1:],
                        }
                        self._halt_r3(role_id, result)
                        self._emit(role_id, "needs_approval")
                        return
                    done.append({"id": call["id"], "name": call["name"], "result": result})
                history.append({"role": "tool", "results": done})
            self._finish_max(role_id)
            self._emit(role_id, "done")
        except AllProvidersFailed as e:
            self._state[role_id] = "error"
            self._detail[role_id] = str(e)[:200]
            self._last_reply[role_id] = str(e)[:500]
            self._emit(role_id, "error")
        except Exception as e:
            self._state[role_id] = "error"
            self._detail[role_id] = str(e)[:200]
            self._last_reply[role_id] = f"error: {e}"[:500]
            self._emit(role_id, "error")

    def _run_video(self, role_id: str, providers: list) -> None:
        """Deterministic Video Studio pipeline (no tool loop); progress goes to the agent card."""
        from video_studio.pipeline import Cancelled, default_deps, run_job

        def progress(msg: str, replace: bool = False) -> None:
            msg = str(msg)[:160]
            steps = self._steps[role_id]
            if replace and steps and steps[-1].startswith(("rendering ", "downloading ffmpeg")):
                steps[-1] = msg
            else:
                steps.append(msg)
            self._detail[role_id] = msg[:80]
            if not replace and msg[:2] in ("1/", "2/", "3/", "4/", "5/"):
                self._emit(role_id, "progress")

        def on_provider(name: str) -> None:
            if name and self._provider[role_id] != name:
                self._provider[role_id] = name
                self._steps[role_id].append(f"provider: {PROVIDER_LABEL.get(name, name)}")

        try:
            factory = self.video_deps or default_deps
            deps = factory(self.root, providers, progress=progress, on_provider=on_provider)
            res = run_job(self.root, self._goals[role_id], deps, progress=progress,
                          should_stop=self._stop[role_id].is_set)
        except Cancelled:
            self._detail[role_id] = "stopped"
            self._state[role_id] = "standby"
            self._last_reply[role_id] = "Video stopped before it finished."
            return
        except Exception as e:  # noqa: BLE001
            self._state[role_id] = "error"
            self._detail[role_id] = f"video failed: {e}"[:200]
            self._last_reply[role_id] = f"video failed: {e}"[:500]
            self._emit(role_id, "error")
            return
        for f in res.get("files") or []:
            self.note_file(role_id, f)
        self._folder[role_id] = res["folder"]
        mins = res["timings"]["total"] / 60
        self._last_reply[role_id] = (
            f"Video ready: \"{res['title']}\" — {res['duration']:.0f} seconds, {res['scenes']} scenes, "
            f"made in {mins:.1f} minutes. Topic: {res['topic']}. Saved in workspace/{res['rel']}. "
            "Not uploaded; review it first."
        )[:2000]
        self._steps[role_id].append("final")
        self._detail[role_id] = "done"
        self._state[role_id] = "standby"
        self._emit(role_id, "done")

    def _exec_tool(self, role_id, tools, allowed, name, args):
        if name not in allowed:
            msg = f"blocked tool {name}"
            self._steps[role_id].append(msg)
            return {"ok": False, "error": msg}
        if name == "write_file":
            content = str((args or {}).get("content") or "")
            self._steps[role_id].append(
                f"write_file {str((args or {}).get('path'))[:80]} ({len(content.encode('utf-8'))} B): "
                + content[:60].replace("\n", " ")
            )
        else:
            self._steps[role_id].append(
                f"{name}({json.dumps(args, ensure_ascii=False)[:120]})"
            )
        mcp = self._mcp_maps.get(role_id, {}).get(name)
        if mcp:
            # Every MCP tool call is R3; the model can never mark it confirmed.
            return {"ok": False, "needs_r3": True, "kind": "mcp", "server": mcp["server"],
                    "tool": mcp["tool"], "args": dict(args or {})}
        result = tools.call(name, args)
        if name == "write_file" and isinstance(result, dict) and result.get("ok"):
            self.note_file(role_id, (result.get("data") or {}).get("path", ""))
        if isinstance(result, dict) and not result.get("ok") and not result.get("needs_r3") and result.get("error"):
            self._steps[role_id].append(f"  ↳ {name} failed: {str(result['error'])[:100]}")
        return result

    def _halt_r3(self, role_id: str, result: dict) -> None:
        kind = result.get("kind")
        if kind in ("mcp", "screen", "file"):
            token = uuid.uuid4().hex[:12]
            if kind == "mcp":
                label = f"MCP {result.get('server')}.{result.get('tool')}"
                pend = {"kind": "mcp", "server": str(result.get("server")), "tool": str(result.get("tool")),
                        "args": result.get("args") or {}, "token": token, "label": label}
            elif kind == "file":
                op = str(result.get("op") or "")
                label = f"{'Overwrite' if op == 'overwrite' else 'Delete'} workspace/{result.get('path')}"
                pend = {"kind": "file", "op": op, "path": str(result.get("path")),
                        "content": str(result.get("content") or ""), "token": token, "label": label}
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
        if result.get("cwd"):
            self._pending_shell_cwd[role_id] = str(result["cwd"])
        self._steps[role_id].append(f"needs_r3: {cmd[:120]}")
        self._detail[role_id] = "needs_r3:" + cmd
        self._last_reply[role_id] = (
            f"Shell command needs operator R3 approval: {cmd}"
            + (f" (in workspace/{result['cwd']})" if result.get("cwd") else "")
        )[:2000]
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
    if p.get("kind") == "file":
        out["op"] = p.get("op")
        out["path"] = p.get("path")
        out["args_preview"] = str(p.get("content") or "")[:400]
    elif p.get("kind") == "mcp":
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
