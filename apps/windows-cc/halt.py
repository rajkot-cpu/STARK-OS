# apps/windows-cc/halt.py
"""Emergency STOP (Master Upgrade Module 1A).

One kill switch for all of Jarvis. Four triggers feed it:
  * global hotkey Ctrl+Alt+Shift+S  (hotkey_win.py)
  * typed or spoken "stop" / "jarvis stop" / "stop everything"  (voice_intents.py)
  * a file named STOP in the Jarvis folder  (watch thread below)
  * the STOP button in the HUD  (bridge_api.halt_stop)

When STOP fires: new tasks are refused, queued/pending actions are cancelled, running
agents (and their shell / video child processes) are stopped, wake word and speech stop,
logs and state are kept. The stopped state is saved to logs/halt_state.json, so a restart
stays stopped. Nothing resumes on its own: resume needs the operator to type RESUME (or
press Resume and type it) while no STOP file exists.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

_IST = timezone(timedelta(hours=5, minutes=30))
RESUME_WORD = "RESUME"
STATE_NAME = "halt_state.json"
STOP_FILE_NAME = "STOP"


def _now() -> str:
    return datetime.now(_IST).isoformat(timespec="seconds")


# ---- child-process registry (shell commands, ffmpeg) so STOP can kill them ----

_procs: set = set()
_procs_lock = threading.Lock()


def register_process(p) -> None:
    with _procs_lock:
        for old in [q for q in _procs if _poll(q) is not None]:
            _procs.discard(old)  # drop finished processes
        _procs.add(p)


def _poll(p):
    try:
        return p.poll()
    except Exception:
        return 0


def unregister_process(p) -> None:
    with _procs_lock:
        _procs.discard(p)


def kill_registered_processes() -> int:
    """Terminate every registered child process tree. Returns how many were still running."""
    with _procs_lock:
        procs = list(_procs)
    n = 0
    for p in procs:
        try:
            if p.poll() is not None:
                continue
            n += 1
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                               timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                p.kill()
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    return n


def run_tracked(args, **kw) -> subprocess.CompletedProcess:
    """subprocess.run replacement whose child STOP can kill. Refuses to start while halted."""
    ctl = current()
    if ctl is not None and ctl.is_stopped():
        raise HaltedError("Emergency STOP is active")
    timeout = kw.pop("timeout", None)
    inp = kw.pop("input", None)
    capture = kw.pop("capture_output", False)
    if capture:
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    if inp is not None:
        kw.setdefault("stdin", subprocess.PIPE)
    p = subprocess.Popen(args, **kw)
    register_process(p)
    try:
        try:
            out, err = p.communicate(input=inp, timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            raise
    finally:
        unregister_process(p)
    return subprocess.CompletedProcess(args, p.returncode, out, err)


class HaltedError(RuntimeError):
    pass


# ---- controller ----

_current: "HaltController | None" = None


def current() -> "HaltController | None":
    return _current


def set_current(ctl: "HaltController | None") -> None:
    global _current
    _current = ctl


class HaltController:
    def __init__(self, root: Path | str, audit: Callable[..., None] | None = None):
        self.root = Path(root)
        self.stop_file = self.root / STOP_FILE_NAME
        self.state_path = self.root / "logs" / STATE_NAME
        self._audit_fn = audit
        self._lock = threading.RLock()
        self._handlers: list[tuple[str, Callable[[], object]]] = []
        self._watch: threading.Thread | None = None
        self._watch_stop = threading.Event()
        self._state = self._load()

    # persistence
    def _load(self) -> dict:
        try:
            d = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return {"stopped": bool(d.get("stopped")), "since": str(d.get("since") or ""),
                        "source": str(d.get("source") or ""), "reason": str(d.get("reason") or ""),
                        "report": d.get("report") or {}}
        except Exception:
            pass
        return {"stopped": False, "since": "", "source": "", "reason": "", "report": {}}

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
            os.replace(tmp, self.state_path)
        except Exception:
            pass

    def _audit(self, action: str, result: str) -> None:
        fn = self._audit_fn
        if fn is None:
            try:
                from cc_settings import audit as fn  # type: ignore
            except Exception:
                return
        try:
            fn(self.root, "safety", action, result, "")
        except Exception:
            pass

    # handlers run on STOP, in registration order, each isolated
    def on_stop(self, name: str, fn: Callable[[], object]) -> None:
        with self._lock:
            self._handlers.append((name, fn))

    def stop_file_present(self) -> bool:
        try:
            return self.stop_file.exists()
        except Exception:
            return False

    def is_stopped(self) -> bool:
        return bool(self._state.get("stopped")) or self.stop_file_present()

    def status(self) -> dict:
        s = dict(self._state)
        s["stopped"] = self.is_stopped()
        s["stop_file"] = str(self.stop_file)
        s["stop_file_present"] = self.stop_file_present()
        s["resume_word"] = RESUME_WORD
        s["can_resume"] = s["stopped"] and not s["stop_file_present"]
        return s

    def stop(self, source: str, reason: str = "") -> dict:
        """Trigger STOP. Safe to call repeatedly; handlers run every time (idempotent kills)."""
        with self._lock:
            first = not self._state.get("stopped")
            if first:
                self._state.update({"stopped": True, "since": _now(), "source": str(source)[:40],
                                    "reason": str(reason)[:200]})
                self._save()
            handlers = list(self._handlers)
        report: dict = {}
        for name, fn in handlers:
            try:
                r = fn()
                report[name] = r if isinstance(r, (int, str, bool)) or r is None else str(r)[:200]
            except Exception as e:  # one failing handler never blocks the others
                report[name] = f"error: {type(e).__name__}: {e}"[:200]
        report["child_processes_killed"] = kill_registered_processes()
        with self._lock:
            if first:
                self._state["report"] = report
                self._save()
        self._audit("emergency_stop" if first else "emergency_stop_repeat",
                    f"source={source} reason={str(reason)[:120]} report={json.dumps(report)[:300]}")
        return {"ok": True, "data": self.status() | {"report": report}}

    def resume(self, source: str, typed: str = "") -> dict:
        with self._lock:
            if not self.is_stopped():
                return {"ok": True, "data": self.status() | {"note": "not stopped"}}
            if self.stop_file_present():
                self._audit("resume_refused", f"source={source} STOP file still present")
                return {"ok": False, "error": f"Delete the STOP file first: {self.stop_file}"}
            if str(typed or "").strip().upper() != RESUME_WORD:
                self._audit("resume_refused", f"source={source} wrong confirmation word")
                return {"ok": False, "error": f"Type {RESUME_WORD} to resume"}
            self._state.update({"stopped": False, "since": "", "source": "", "reason": "", "report": {}})
            self._save()
        self._audit("resume", f"source={source}; stopped tasks were NOT restarted")
        return {"ok": True, "data": self.status()}

    # STOP-file watcher
    def start_watch(self, interval: float = 1.0) -> None:
        if self._watch and self._watch.is_alive():
            return
        self._watch_stop.clear()

        def loop():
            while not self._watch_stop.wait(interval):
                try:
                    if self.stop_file_present() and not self._state.get("stopped"):
                        self.stop("stop_file", f"STOP file found at {self.stop_file}")
                except Exception:
                    pass

        self._watch = threading.Thread(target=loop, name="halt-stopfile-watch", daemon=True)
        self._watch.start()

    def stop_watch(self) -> None:
        self._watch_stop.set()

    def check_once(self) -> bool:
        """Poll once (tests / startup): STOP file present -> trigger stop. Returns stopped."""
        if self.stop_file_present() and not self._state.get("stopped"):
            self.stop("stop_file", f"STOP file found at {self.stop_file}")
        return self.is_stopped()
