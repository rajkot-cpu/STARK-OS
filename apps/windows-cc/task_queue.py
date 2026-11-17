# apps/windows-cc/task_queue.py
"""Persistent task queue (Phase 3) at <root>/data/tasks.db — survives restarts.

Adapted from the v7 bundle's agent_orchestrator.py crash-recovery pattern (its hardcoded
ag1..ag10 trading roster was not kept). On start-up, tasks left RUNNING are marked
'interrupted' and QUEUED stay queued; nothing auto-runs after a restart or a STOP —
the operator presses Retry / Run. Results are stored per step.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
STATES = ("queued", "running", "done", "error", "cancelled", "interrupted")
_locks: dict[str, threading.Lock] = {}


def _now() -> str:
    return datetime.now(_IST).isoformat(timespec="seconds")


class TaskQueue:
    def __init__(self, root: Path | str, path: Path | str | None = None):
        self.root = Path(root)
        self.path = Path(path) if path else self.root / "data" / "tasks.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _locks.setdefault(str(self.path), threading.Lock())
        with self._lock, self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS tasks(
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, step INTEGER NOT NULL DEFAULT 0, steps TEXT NOT NULL DEFAULT '[]',
                result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'ui',
                created TEXT NOT NULL, updated TEXT NOT NULL)""")

    @contextmanager
    def _conn(self):
        """Commit and CLOSE every connection (an unclosed handle locks the file on Windows)."""
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def recover(self) -> int:
        """Call once at start-up: RUNNING -> interrupted (never auto-resumed)."""
        with self._lock, self._conn() as c:
            n = c.execute("UPDATE tasks SET state='interrupted', error='Jarvis restarted while this was running',"
                          " updated=? WHERE state='running'", (_now(),)).rowcount
        return int(n)

    def add(self, kind: str, title: str, payload: dict, source: str = "ui") -> dict:
        tid = uuid.uuid4().hex[:12]
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO tasks(id, kind, title, payload, state, created, updated, source) VALUES (?,?,?,?,?,?,?,?)",
                      (tid, str(kind)[:40], str(title)[:300], json.dumps(payload or {}), "queued", _now(), _now(),
                       str(source)[:20]))
        return self.get(tid)

    def update(self, tid: str, **fields) -> None:
        allowed = {"state", "step", "steps", "result", "error"}
        sets = {k: (json.dumps(v) if k == "steps" else v) for k, v in fields.items() if k in allowed}
        if "state" in sets and sets["state"] not in STATES:
            raise ValueError("bad state")
        if not sets:
            return
        cols = ", ".join(f"{k}=?" for k in sets) + ", updated=?"
        with self._lock, self._conn() as c:
            c.execute(f"UPDATE tasks SET {cols} WHERE id=?", list(sets.values()) + [_now(), tid])

    def claim(self, tid: str) -> bool:
        """queued/interrupted -> running, atomically. False if someone else has it."""
        with self._lock, self._conn() as c:
            n = c.execute("UPDATE tasks SET state='running', error='', updated=? WHERE id=? AND state IN "
                          "('queued','interrupted','error')", (_now(), tid)).rowcount
        return n == 1

    def cancel_running(self, why: str = "Emergency STOP") -> int:
        with self._lock, self._conn() as c:
            n = c.execute("UPDATE tasks SET state='cancelled', error=?, updated=? WHERE state IN ('running','queued')",
                          (why, _now())).rowcount
        return int(n)

    def cancel(self, tid: str) -> bool:
        with self._lock, self._conn() as c:
            n = c.execute("UPDATE tasks SET state='cancelled', error='cancelled by operator', updated=? "
                          "WHERE id=? AND state IN ('queued','running','interrupted','error')", (_now(), tid)).rowcount
        return n == 1

    def get(self, tid: str) -> dict | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM tasks WHERE id=?", (str(tid),)).fetchone()
        return self._row(r) if r else None

    def list(self, limit: int = 30) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = list(c.execute("SELECT * FROM tasks ORDER BY created DESC, rowid DESC LIMIT ?", (int(limit),)))
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        for k in ("payload", "steps"):
            try:
                d[k] = json.loads(d[k] or ("{}" if k == "payload" else "[]"))
            except Exception:
                d[k] = {} if k == "payload" else []
        return d
