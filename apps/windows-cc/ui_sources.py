# apps/windows-cc/ui_sources.py
"""Read-only facts for the v3 HUD: local AI (Ollama) and the data sources agents can use.

Nothing here starts, installs or downloads anything. Market data is never connected in this build.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/tags"


def _ollama_exe() -> str | None:
    cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    if os.environ.get("LOCALAPPDATA") and cand.is_file():
        return str(cand)
    return shutil.which("ollama")


def _tags(timeout: float = 0.8) -> dict | None:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=timeout) as r:  # local only
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def local_ai() -> dict:
    exe = _ollama_exe()
    if not exe:
        return {"ollama": {"state": "not_installed", "models": []}}
    tags = _tags()
    if tags is None:
        return {"ollama": {"state": "not_running", "models": []}}
    models = [str(m.get("name") or "") for m in (tags.get("models") or []) if m.get("name")]
    return {"ollama": {"state": "ready" if models else "no_models", "models": models}}


def data_sources(root: Path) -> list[dict]:
    root = Path(root)
    rows: list[dict] = []
    try:
        import importlib.util

        ws_ok = importlib.util.find_spec("ddgs") is not None
    except Exception:
        ws_ok = False
    rows.append({"id": "web_search", "label": "Web search", "state": "connected" if ws_ok else "unavailable",
                 "detail": "DuckDuckGo (no key), Gemini grounding fallback" if ws_ok else "ddgs package missing"})
    try:
        from memory_index import build

        m = build(root)
        rows.append({"id": "memory", "label": "Memory", "state": "connected" if m["nodes"] else "empty",
                     "detail": f"{m['nodes']} files in {len(m['sources'])} sources"})
    except Exception as e:
        rows.append({"id": "memory", "label": "Memory", "state": "unavailable", "detail": type(e).__name__})
    ws = root / "workspace"
    n = sum(1 for p in ws.rglob("*") if p.is_file()) if ws.is_dir() else 0
    rows.append({"id": "files", "label": "Files (workspace)", "state": "connected" if n else "empty",
                 "detail": f"{n} files in jarvis\\workspace"})
    try:
        import mcp_client

        servers, _err = mcp_client.load_servers(root)
        on = [s for s in servers if s.get("enabled")]
        rows.append({"id": "mcp", "label": "MCP tools", "state": "connected" if on else "not_connected",
                     "detail": f"{len(on)} of {len(servers)} servers enabled"})
    except Exception as e:
        rows.append({"id": "mcp", "label": "MCP tools", "state": "unavailable", "detail": type(e).__name__})
    rows.append({"id": "market_data", "label": "Market data", "state": "not_connected",
                 "detail": "No market data source is connected (paper/analysis only when added)"})
    return rows
