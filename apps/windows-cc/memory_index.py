# apps/windows-cc/memory_index.py
from __future__ import annotations

from pathlib import Path

_CANDIDATES = ("STATE.md", "journal", "memory", "notes", "reports")


def build(root: Path, recent: int = 8) -> dict:
    """Count what Jarvis can recall from. Real files only; nothing is invented."""
    root = Path(root)
    sources: list[str] = []
    by_source: dict[str, int] = {}
    found: list[Path] = []
    for name in _CANDIDATES:
        p = root / name
        if p.is_file():
            files = [p]
        elif p.is_dir():
            files = [x for x in p.rglob("*") if x.is_file()]
        else:
            files = []
        if files:
            sources.append(name)
            by_source[name] = len(files)
            found.extend(files)
    nodes = len(found)
    size = 0
    stamped = []
    for f in found:
        try:
            st = f.stat()
            size += st.st_size
            stamped.append((st.st_mtime, f.name))
        except OSError:
            pass
    stamped.sort(reverse=True)
    return {
        "nodes": nodes,
        "edges": max(0, nodes - 1) if nodes else 0,
        "sources": sources,
        "by_source": by_source,
        "bytes": size,
        "recent": [n for _, n in stamped[:recent]],
        "candidates": len(_CANDIDATES),
    }
