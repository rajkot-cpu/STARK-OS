# apps/windows-cc/jarvis_api.py
"""Local HTTP API for Jarvis (Phase 3) — loopback only, token-protected, STOP-aware.

  Base URL : http://127.0.0.1:<api_port>/v1     (api_port in Settings, default 8765)
  Auth     : header  Authorization: Bearer <token>   (or X-Jarvis-Token: <token>)
  Token    : Windows Credential Manager, generic credential "JARVIS/JARVIS_API_TOKEN"
             (created on first start; Settings > Local API can copy or rotate it).

Safety:
  * binds 127.0.0.1 only; Host header must be 127.0.0.1/localhost (DNS-rebinding guard);
    requests with a browser Origin header are refused (no CORS), so web pages can't call it;
  * while Emergency STOP is active every endpoint except GET /v1/status and POST /v1/stop
    answers 423 Locked; there is NO resume endpoint (resume = typed RESUME in the window);
  * R3/R4 approvals cannot be given over the API — agents that need one wait for the
    operator in the app; there are no order endpoints (paper or live);
  * every call is written to the hash-chained audit log (method, path, status; never bodies).
"""
from __future__ import annotations

import hmac
import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN_NAME = "JARVIS_API_TOKEN"
MAX_BODY = 64 * 1024

ENDPOINTS = [
    ("GET", "/v1", "This list"),
    ("GET", "/v1/status", "Version, STOP state, AI routing, local model, agents running (works during STOP)"),
    ("GET", "/v1/readiness", "Weighted readiness score"),
    ("POST", "/v1/ask", 'Ask the AI: {"text": "...", "local": false} -> hybrid router (local=true: Ollama first)'),
    ("POST", "/v1/chat", 'Jarvis persona short reply: {"text": "..."}'),
    ("POST", "/v1/command", 'Same as the command bar (may start an agent): {"text": "..."}'),
    ("GET", "/v1/agents", "List the 8 agents and their state"),
    ("POST", "/v1/agents/{id}/run", 'Start an agent: {"goal": "..."}; R3 steps wait for approval in the app'),
    ("POST", "/v1/agents/{id}/stop", "Stop one agent"),
    ("POST", "/v1/chain", 'Research -> Analyst -> Writer: {"topic": "..."} -> task id; report saved to workspace/reports'),
    ("GET", "/v1/tasks", "Persistent task queue (latest 30)"),
    ("GET", "/v1/tasks/{id}", "One task with per-step provider/timing and result file"),
    ("GET", "/v1/memory/search?q=...&limit=20", "Full-text search over Jarvis memory"),
    ("POST", "/v1/memory/note", 'Save a note: {"title": "...", "text": "..."}'),
    ("GET", "/v1/trading/snapshot?symbol=NIFTY&tf=1d", "Real indicators/pivots/regime from keyless delayed data (read-only)"),
    ("GET", "/v1/trading/paper", "Paper ledger (read-only; orders only from the app)"),
    ("POST", "/v1/stop", 'Emergency STOP: {"reason": "..."} (always allowed)'),
    ("POST", "/v1/resume", "Always refused: resume only by typing RESUME in the Jarvis window"),
]


def get_or_create_token(store=None) -> str:
    """Read the API token from Credential Manager, creating it once. Never printed."""
    if store is None:
        import secrets_store as store
    if not store.available():
        return ""
    tok = store.read(TOKEN_NAME)
    if tok:
        return tok
    tok = secrets.token_urlsafe(32)
    if store.write(TOKEN_NAME, tok) and store.read(TOKEN_NAME) == tok:
        return tok
    return ""


def rotate_token(store=None) -> bool:
    if store is None:
        import secrets_store as store
    if not store.available():
        return False
    tok = secrets.token_urlsafe(32)
    return bool(store.write(TOKEN_NAME, tok) and store.read(TOKEN_NAME) == tok)


class LocalApi:
    def __init__(self, bridge, port: int = 8765, token_fn=None, audit=None):
        self.bridge = bridge
        self.port = int(port)
        self.token_fn = token_fn or get_or_create_token
        self.audit = audit
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.error = ""
        self.requests = 0

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self) -> dict:
        if self.running:
            return {"ok": True, "data": {"port": self.port}}
        if not self.token_fn():
            self.error = "no secure token store (Windows Credential Manager unavailable); API not started"
            return {"ok": False, "error": self.error}
        api = self

        class Handler(_Handler):
            owner = api

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as e:
            self.error = f"port {self.port} unavailable ({e.__class__.__name__})"
            return {"ok": False, "error": self.error}
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="jarvis-local-api")
        self.thread.start()
        self.error = ""
        return {"ok": True, "data": {"port": self.port}}

    def stop(self) -> None:
        s, self.server = self.server, None
        if s:
            s.shutdown()
            s.server_close()

    def info(self) -> dict:
        return {"running": self.running, "port": self.port, "base": f"http://127.0.0.1:{self.port}/v1",
                "error": self.error, "requests": self.requests,
                "token_location": "Windows Credential Manager -> JARVIS/JARVIS_API_TOKEN",
                "endpoints": [{"method": m, "path": p, "desc": d} for m, p, d in ENDPOINTS]}


class _Handler(BaseHTTPRequestHandler):
    owner: LocalApi
    server_version = "JarvisLocalAPI/1"
    sys_version = ""

    def log_message(self, fmt, *args):  # no stderr noise (windowed exe)
        pass

    # ---- plumbing ----
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
        self._audit(code)

    def _audit(self, code: int) -> None:
        o = self.owner
        o.requests += 1
        if o.audit:
            try:
                o.audit("local-api", "api_call", f"{self.command} {urlparse(self.path).path} -> {code}")
            except Exception:
                pass

    def _guard(self) -> bool:
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._send(403, {"ok": False, "error": "loopback only"})
            return False
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            self._send(403, {"ok": False, "error": "bad Host header"})
            return False
        if self.headers.get("Origin"):
            self._send(403, {"ok": False, "error": "browser requests are not allowed"})
            return False
        expected = self.owner.token_fn() or ""
        auth = self.headers.get("Authorization") or ""
        got = auth[7:].strip() if auth.lower().startswith("bearer ") else (self.headers.get("X-Jarvis-Token") or "").strip()
        if not expected or not got or not hmac.compare_digest(got.encode(), expected.encode()):
            self._send(401, {"ok": False, "error": "missing or wrong token (see Settings > Local API)"})
            return False
        return True

    def _body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            self._send(413, {"ok": False, "error": "body too large"})
            return None
        if n == 0:
            return {}
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(d, dict):
                raise ValueError
            return d
        except Exception:
            self._send(400, {"ok": False, "error": "body must be a JSON object"})
            return None

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._send(405, {"ok": False, "error": "method not allowed"})

    do_DELETE = do_PATCH = do_PUT

    # ---- routing ----
    def _dispatch(self, method: str) -> None:
        try:
            if not self._guard():
                return
            u = urlparse(self.path)
            path = u.path.rstrip("/") or "/"
            q = {k: v[-1] for k, v in parse_qs(u.query).items()}
            body = {}
            if method == "POST":
                body = self._body()
                if body is None:
                    return
            b = self.owner.bridge
            halted = b._stopped()
            if method == "POST" and path == "/v1/stop":
                r = b.halt_stop("api", str(body.get("reason") or "STOP via local API")[:200])
                return self._send(200, r)
            if method == "POST" and path == "/v1/resume":
                return self._send(403, {"ok": False, "error": "Resume is only possible in the Jarvis window "
                                                              "(type RESUME). The API cannot resume."})
            if method == "GET" and path == "/v1/status":
                return self._send(200, b.api_status())
            if halted:
                return self._send(423, {"ok": False, "halted": True,
                                        "error": "Emergency STOP is active; the API is blocked until you type RESUME in Jarvis."})
            code, out = self._route(method, path, q, body, b)
            return self._send(code, out)
        except Exception as e:
            try:
                self._send(500, {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            except Exception:
                pass

    def _route(self, method, path, q, body, b):
        if method == "GET":
            if path == "/v1":
                return 200, {"ok": True, "data": self.owner.info()["endpoints"]}
            if path == "/v1/readiness":
                return 200, b.readiness()
            if path == "/v1/agents":
                r = b.agents()
                if r.get("ok"):
                    r["data"]["agents"] = [{k: a.get(k) for k in ("id", "name", "state", "detail", "goal", "provider",
                                                                  "last_reply", "files", "pending")}
                                           for a in r["data"]["agents"]]
                return 200, r
            if path == "/v1/tasks":
                return 200, b.tasks_list(int(q.get("limit", 30)))
            m = re.fullmatch(r"/v1/tasks/([0-9a-f]{6,32})", path)
            if m:
                r = b.task_get(m.group(1))
                return (200 if r.get("ok") else 404), r
            if path == "/v1/memory/search":
                return 200, b.memory_search(q.get("q", ""), int(q.get("limit", 20)))
            if path == "/v1/trading/snapshot":
                return 200, b.trading_snapshot(q.get("symbol", "NIFTY"), q.get("tf", "1d"))
            if path == "/v1/trading/paper":
                return 200, b.paper_summary()
            return 404, {"ok": False, "error": "unknown endpoint; GET /v1 lists them"}
        # POST
        if path == "/v1/ask":
            return 200, b.ask(str(body.get("text") or ""), bool(body.get("local")))
        if path == "/v1/chat":
            return 200, b.chat(str(body.get("text") or ""))
        if path == "/v1/command":
            return 200, b.command(str(body.get("text") or ""))
        m = re.fullmatch(r"/v1/agents/([a-z]{2,20})/(run|stop)", path)
        if m:
            if m.group(2) == "run":
                return 200, b.agent_start(m.group(1), str(body.get("goal") or ""))
            return 200, b.agent_stop(m.group(1))
        if path == "/v1/chain":
            return 200, b.chain_start(str(body.get("topic") or ""), source="api")
        if path == "/v1/memory/note":
            return 200, b.memory_note_add(str(body.get("title") or ""), str(body.get("text") or ""), source="api")
        return 404, {"ok": False, "error": "unknown endpoint; GET /v1 lists them"}
