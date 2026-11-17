# apps/windows-cc/memory_db.py
"""Persistent memory with full-text search (Phase 3).

SQLite at <root>/data/memory.db. FTS5 when available (LIKE fallback otherwise). Holds notes
Jarvis writes (agent results, chain reports, trading journal) plus an index of the operator's
own memory files (STATE.md, journal/, memory/, notes/, reports/). Adapted from the v7 bundle's
memory_vault_db.py (search + journal ideas); its separate kill switch was not kept — STOP is halt.py.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
SOURCES = ("STATE.md", "journal", "memory", "notes", "reports", "workspace/reports")
TEXT_EXT = {".md", ".txt", ".json", ".jsonl", ".csv", ".yaml", ".yml", ".html", ".py", ".log"}
MAX_FILE = 256 * 1024
MAX_FILES = 3000
_locks: dict[str, threading.Lock] = {}


def _now() -> str:
    return datetime.now(_IST).isoformat(timespec="seconds")


class MemoryDB:
    def __init__(self, root: Path | str, path: Path | str | None = None):
        self.root = Path(root)
        self.path = Path(path) if path else self.root / "data" / "memory.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _locks.setdefault(str(self.path), threading.Lock())
        self.fts = False
        with self._lock, self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS notes(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL,
                title TEXT NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '', digest TEXT NOT NULL DEFAULT '')""")
            c.execute("CREATE INDEX IF NOT EXISTS notes_source ON notes(source)")
            try:
                c.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    title, body, tags, content='notes', content_rowid='id', tokenize='unicode61')""")
                c.executescript("""
                CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                  INSERT INTO notes_fts(rowid, title, body, tags) VALUES (new.id, new.title, new.body, new.tags); END;
                CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags) VALUES('delete', old.id, old.title, old.body, old.tags); END;
                CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                  INSERT INTO notes_fts(notes_fts, rowid, title, body, tags) VALUES('delete', old.id, old.title, old.body, old.tags);
                  INSERT INTO notes_fts(rowid, title, body, tags) VALUES (new.id, new.title, new.body, new.tags); END;
                """)
                self.fts = True
            except sqlite3.OperationalError:
                self.fts = False

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        return c

    # ---- write ----
    def add(self, kind: str, title: str, body: str, source: str = "", tags: str = "") -> int:
        body = str(body or "")
        digest = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()[:32]
        with self._lock, self._conn() as c:
            cur = c.execute("INSERT INTO notes(ts, kind, title, body, source, tags, digest) VALUES (?,?,?,?,?,?,?)",
                            (_now(), str(kind)[:40], str(title)[:300], body, str(source)[:500], str(tags)[:300], digest))
            return int(cur.lastrowid)

    def reindex_files(self) -> dict:
        """Index the operator's memory files (new/changed only). Never edits those files."""
        t0 = time.time()
        seen, added, updated, skipped = 0, 0, 0, 0
        files: list[Path] = []
        for name in SOURCES:
            p = self.root / name
            if p.is_file():
                files.append(p)
            elif p.is_dir():
                files.extend(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in TEXT_EXT)
            if len(files) >= MAX_FILES:
                break
        with self._lock, self._conn() as c:
            known = {r["source"]: (r["id"], r["digest"]) for r in
                     c.execute("SELECT id, source, digest FROM notes WHERE kind='file'")}
            for f in files[:MAX_FILES]:
                try:
                    if f.stat().st_size > MAX_FILE:
                        skipped += 1
                        continue
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    skipped += 1
                    continue
                seen += 1
                rel = str(f.relative_to(self.root)).replace("\\", "/")
                digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:32]
                if rel in known:
                    if known[rel][1] == digest:
                        continue
                    c.execute("UPDATE notes SET ts=?, body=?, digest=? WHERE id=?", (_now(), text, digest, known[rel][0]))
                    updated += 1
                else:
                    c.execute("INSERT INTO notes(ts, kind, title, body, source, tags, digest) VALUES (?,?,?,?,?,?,?)",
                              (_now(), "file", f.name, text, rel, rel.split("/")[0], digest))
                    added += 1
        return {"files": seen, "added": added, "updated": updated, "skipped": skipped,
                "seconds": round(time.time() - t0, 2)}

    # ---- read ----
    @staticmethod
    def _fts_query(q: str) -> str:
        toks = re.findall(r"[\w\u0900-\u097F]+", str(q or ""), flags=re.UNICODE)[:12]
        return " ".join(f'"{t}"*' for t in toks)

    def search(self, q: str, limit: int = 20, kind: str = "") -> list[dict]:
        q = str(q or "").strip()
        limit = max(1, min(int(limit or 20), 100))
        if not q:
            return self.recent(limit, kind)
        with self._lock, self._conn() as c:
            rows = []
            fq = self._fts_query(q)
            if self.fts and fq:
                sql = ("SELECT n.id, n.ts, n.kind, n.title, n.source, "
                       "snippet(notes_fts, 1, '[', ']', ' … ', 18) AS snip FROM notes_fts "
                       "JOIN notes n ON n.id = notes_fts.rowid WHERE notes_fts MATCH ?")
                args: list = [fq]
                if kind:
                    sql += " AND n.kind = ?"
                    args.append(kind)
                sql += " ORDER BY bm25(notes_fts) LIMIT ?"
                args.append(limit)
                try:
                    rows = list(c.execute(sql, args))
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                like = f"%{q}%"
                sql = ("SELECT id, ts, kind, title, source, substr(body, 1, 160) AS snip FROM notes "
                       "WHERE (title LIKE ? OR body LIKE ?)" + (" AND kind = ?" if kind else "") +
                       " ORDER BY id DESC LIMIT ?")
                rows = list(c.execute(sql, [like, like] + ([kind] if kind else []) + [limit]))
        return [{"id": r["id"], "ts": r["ts"], "kind": r["kind"], "title": r["title"], "source": r["source"],
                 "snippet": " ".join(str(r["snip"] or "").split())[:300]} for r in rows]

    def recent(self, limit: int = 20, kind: str = "") -> list[dict]:
        with self._lock, self._conn() as c:
            sql = "SELECT id, ts, kind, title, source, substr(body,1,160) AS snip FROM notes"
            args: list = []
            if kind:
                sql += " WHERE kind = ?"
                args.append(kind)
            else:
                sql += " WHERE kind != 'file'"
            rows = list(c.execute(sql + " ORDER BY id DESC LIMIT ?", args + [int(limit)]))
        return [{"id": r["id"], "ts": r["ts"], "kind": r["kind"], "title": r["title"], "source": r["source"],
                 "snippet": " ".join(str(r["snip"] or "").split())[:300]} for r in rows]

    def get(self, note_id: int) -> dict | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM notes WHERE id=?", (int(note_id),)).fetchone()
        return dict(r) if r else None

    def stats(self) -> dict:
        with self._lock, self._conn() as c:
            by = {r["kind"]: r["n"] for r in c.execute("SELECT kind, COUNT(*) AS n FROM notes GROUP BY kind")}
        return {"total": sum(by.values()), "by_kind": by, "fts": self.fts, "path": str(self.path)}
