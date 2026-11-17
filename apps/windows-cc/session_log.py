# apps/windows-cc/session_log.py
"""Crash / exit diagnostics for the silent window closes.

* logs/session.json records the running session (pid, start time, clean flag, last heartbeat
  with memory use). On the next start, a session that never marked itself clean is reported
  in logs/ui-errors.log as an unexpected end (crash, kill, power loss) with its last heartbeat.
* faulthandler writes native crash tracebacks (e.g. a DLL access violation) to
  logs/crash-native.log, which plain Python exception hooks never see.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

_fault_file = None


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process().memory_info().rss / 1e6, 1)
    except Exception:
        return None


class SessionLog:
    def __init__(self, root: Path | str, log=None):
        self.root = Path(root)
        self.path = self.root / "logs" / "session.json"
        self._log = log
        self._hb_stop = threading.Event()
        self.previous: dict | None = None

    def _write(self, d: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            pass

    def _read(self) -> dict | None:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else None
        except Exception:
            return None

    def start(self) -> dict | None:
        """Record this session; return the previous one if it ended unexpectedly."""
        prev = self._read()
        unexpected = None
        if prev and not prev.get("clean"):
            unexpected = prev
            if self._log:
                self._log(self.root, "host.session",
                          f"previous session pid={prev.get('pid')} started {prev.get('started')} ended "
                          f"without a clean exit (crash, kill or power loss); last heartbeat "
                          f"{prev.get('heartbeat')} rss_mb={prev.get('rss_mb')}", "warn")
        self.previous = unexpected
        self._cur = {"pid": os.getpid(), "started": _now(), "clean": False, "heartbeat": _now(),
                     "rss_mb": _rss_mb(), "exit_reason": ""}
        self._write(self._cur)
        return unexpected

    def heartbeat(self) -> None:
        self._cur["heartbeat"] = _now()
        self._cur["rss_mb"] = _rss_mb()
        self._write(self._cur)

    def start_heartbeat(self, interval: float = 30.0) -> None:
        def loop():
            while not self._hb_stop.wait(interval):
                self.heartbeat()

        threading.Thread(target=loop, name="session-heartbeat", daemon=True).start()

    def end(self, reason: str) -> None:
        self._hb_stop.set()
        self._cur["clean"] = True
        self._cur["exit_reason"] = str(reason)[:200]
        self._cur["ended"] = _now()
        self._cur["rss_mb"] = _rss_mb()
        self._write(self._cur)


def enable_faulthandler(root: Path | str) -> bool:
    global _fault_file
    try:
        import faulthandler

        d = Path(root) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        _fault_file = open(d / "crash-native.log", "a", encoding="utf-8")
        _fault_file.write(f"--- session start {_now()} pid={os.getpid()}\n")
        _fault_file.flush()
        faulthandler.enable(file=_fault_file, all_threads=True)
        return True
    except Exception:
        return False
