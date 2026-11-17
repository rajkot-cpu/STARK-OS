# apps/windows-cc/audit_chain.py
"""Tamper-evident (hash-chained) audit log — Master Upgrade Module 1E.

Each new line written by Jarvis carries two extra fields:
  prev = sha256 of the raw previous line in the file ("GENESIS" for the first line)
  hash = sha256(prev + canonical JSON of the line without "hash")
Older lines and lines written by other tools (panel, scripts) are not changed; they are still
covered because the next chained line pins their exact bytes via "prev". Editing, deleting
or reordering any line before the last chained line is detected by `verify()`.

CLI:  python audit_chain.py <path-to-audit.jsonl>     (exit 0 = intact, 1 = problem)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from pathlib import Path

GENESIS = "GENESIS"
_lock = threading.Lock()


def _sha(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def _canon(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _last_line(path: Path) -> bytes | None:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    with path.open("rb") as f:
        chunk = 65536
        pos = size
        buf = b""
        while pos > 0:
            step = min(chunk, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
            stripped = buf.rstrip(b"\r\n")
            i = stripped.rfind(b"\n")
            if i >= 0:
                return stripped[i + 1:]
        stripped = buf.rstrip(b"\r\n")
        return stripped or None


def append(path: Path | str, rec: dict) -> dict:
    """Append rec as one chained JSON line. Returns the written record."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        last = _last_line(p)
        prev = _sha(last.rstrip(b"\r")) if last else GENESIS
        out = {k: v for k, v in rec.items() if k not in ("prev", "hash")}
        out["prev"] = prev
        out["hash"] = _sha(prev + _canon(out))
        data = json.dumps(out, ensure_ascii=False) + "\n"
        # Make sure we start on a fresh line even if another writer left none.
        needs_nl = False
        try:
            if p.stat().st_size > 0:
                with p.open("rb") as f:
                    f.seek(-1, os.SEEK_END)
                    needs_nl = f.read(1) not in (b"\n",)
        except OSError:
            pass
        with p.open("a", encoding="utf-8", newline="\n") as f:
            if needs_nl:
                f.write("\n")
            f.write(data)
    return out


def verify(path: Path | str) -> dict:
    p = Path(path)
    if not p.is_file():
        return {"ok": True, "lines": 0, "chained": 0, "legacy": 0, "problems": [], "note": "no audit log yet"}
    raw = p.read_bytes().split(b"\n")
    if raw and raw[-1] == b"":
        raw = raw[:-1]
    problems: list[dict] = []
    chained = legacy = 0
    started = False
    prev_raw: bytes | None = None
    for i, line in enumerate(raw, start=1):
        line = line.rstrip(b"\r")
        try:
            rec = json.loads(line.decode("utf-8"))
        except Exception:
            rec = None
        if isinstance(rec, dict) and "hash" in rec and "prev" in rec:
            started = True
            chained += 1
            want_prev = _sha(prev_raw) if prev_raw is not None else GENESIS
            if rec["prev"] != want_prev:
                problems.append({"line": i, "problem": "previous line was changed, removed or reordered"})
            if rec["hash"] != _sha(str(rec["prev"]) + _canon(rec)):
                problems.append({"line": i, "problem": "this line was edited"})
        else:
            legacy += 1
            if rec is None and line.strip():
                problems.append({"line": i, "problem": "not valid JSON"}) if started else None
        prev_raw = line
    return {"ok": not problems, "lines": len(raw), "chained": chained, "legacy": legacy,
            "problems": problems[:50]}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "logs/audit.jsonl"
    r = verify(target)
    print(json.dumps(r, indent=2))
    sys.exit(0 if r["ok"] else 1)
