# apps/windows-cc/mcp_client.py
"""MCP client for AgentHub (mcp python-sdk 2.3.x, stdio transport).

Servers come from <root>/config/mcp_servers.json ({"servers": [...]}).
Every MCP tool call is R3: agents only *request* it; the operator confirms
in the UI (BridgeApi.tool_confirm). Tool schemas are sanitized for Gemini
functionDeclarations.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

PREFIX = "mcp_"
LIST_TIMEOUT = 20.0
CALL_TIMEOUT = 60.0
CACHE_TTL = 300.0

_cache: dict = {}
_cache_lock = threading.Lock()
_last_errors: dict = {}

# OpenAPI-subset keys Gemini accepts in functionDeclarations.parameters.
_ALLOWED = {"type", "description", "enum", "properties", "required", "items",
            "nullable", "minimum", "maximum", "minItems", "maxItems", "format"}
_TYPES = {"string", "number", "integer", "boolean", "array", "object"}
_FORMATS = {"enum", "date-time"}
_NAME_RE = re.compile(r"[^A-Za-z0-9_]")


def config_path(root) -> Path:
    return Path(root) / "config" / "mcp_servers.json"


def load_servers(root) -> tuple[list[dict], str]:
    """Return (servers, error). Missing file -> ([], '')."""
    p = config_path(root)
    if not p.is_file():
        return [], ""
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return [], f"invalid JSON: {type(e).__name__}"
    items = raw.get("servers") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return [], "missing 'servers' list"
    out, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            continue
        name = _NAME_RE.sub("_", str(it.get("name") or "")).strip("_")[:20]
        cmd = str(it.get("command") or "").strip()
        if not name or not cmd or name in seen:
            continue
        seen.add(name)
        args = it.get("args") if isinstance(it.get("args"), list) else []
        env = it.get("env") if isinstance(it.get("env"), dict) else None
        out.append({
            "name": name,
            "command": cmd,
            "args": [str(a) for a in args],
            "env": {str(k): str(v) for k, v in env.items()} if env else None,
            "enabled": it.get("enabled", True) is not False,
            "description": str(it.get("description") or "")[:200],
        })
    return out, ""


def public_view(root) -> dict:
    """Read-only info for the Settings page (no env values)."""
    servers, err = load_servers(root)
    return {
        "path": str(config_path(root)),
        "error": err,
        "servers": [
            {"name": s["name"], "command": s["command"], "args": s["args"],
             "enabled": s["enabled"], "description": s["description"],
             "env_keys": sorted((s["env"] or {}).keys()),
             "last_error": _last_errors.get(s["name"], "")}
            for s in servers
        ],
    }


def sanitize_schema(schema, _depth: int = 0) -> dict:
    """Convert a JSON Schema (MCP inputSchema) to Gemini's OpenAPI subset."""
    if not isinstance(schema, dict) or _depth > 8:
        return {"type": "string"}
    s = dict(schema)
    # anyOf/oneOf: pick the first non-null branch.
    for comb in ("anyOf", "oneOf", "allOf"):
        branches = s.get(comb)
        if isinstance(branches, list) and branches:
            non_null = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
            base = non_null[0] if non_null else {"type": "string"}
            merged = {**base, **{k: v for k, v in s.items() if k not in ("anyOf", "oneOf", "allOf")}}
            if len(non_null) < len(branches):
                merged["nullable"] = True
            s = merged
    t = s.get("type")
    nullable = bool(s.get("nullable"))
    if isinstance(t, list):
        nn = [x for x in t if x != "null"]
        nullable = nullable or len(nn) < len(t)
        t = nn[0] if nn else "string"
    if t not in _TYPES:
        t = "object" if isinstance(s.get("properties"), dict) else (
            "array" if "items" in s else "string")
    out: dict = {"type": t}
    if isinstance(s.get("description"), str) and s["description"]:
        out["description"] = s["description"][:500]
    elif isinstance(s.get("title"), str) and s["title"] and _depth > 0:
        out["description"] = s["title"][:200]
    if nullable:
        out["nullable"] = True
    if isinstance(s.get("enum"), list):
        vals = [str(v) for v in s["enum"] if v is not None]
        if vals and t == "string":
            out["enum"] = vals
    if t == "string" and s.get("format") in _FORMATS:
        out["format"] = s["format"]
    if t in ("number", "integer"):
        for k in ("minimum", "maximum"):
            if isinstance(s.get(k), (int, float)) and not isinstance(s.get(k), bool):
                out[k] = s[k]
    if t == "array":
        out["items"] = sanitize_schema(s.get("items") if isinstance(s.get("items"), dict) else {"type": "string"}, _depth + 1)
        for k in ("minItems", "maxItems"):
            if isinstance(s.get(k), int):
                out[k] = s[k]
    if t == "object":
        props = s.get("properties") if isinstance(s.get("properties"), dict) else {}
        clean = {}
        for k, v in props.items():
            clean[str(k)] = sanitize_schema(v, _depth + 1)
        out["properties"] = clean
        req = [r for r in (s.get("required") or []) if isinstance(r, str) and r in clean]
        if req:
            out["required"] = req
    return out


def decl_name(server: str, tool: str) -> str:
    n = f"{PREFIX}{server}_{_NAME_RE.sub('_', tool)}"
    return n[:64]


def _tool_schema(tool) -> dict:
    sch = getattr(tool, "input_schema", None)
    if sch is None:
        sch = getattr(tool, "inputSchema", None)  # mcp 1.x name
    return sch if isinstance(sch, dict) else {"type": "object", "properties": {}}


def _params(server: dict):
    from mcp import StdioServerParameters

    return StdioServerParameters(command=server["command"], args=server["args"], env=server["env"])


def _run(coro, timeout: float):
    import asyncio

    async def guarded():
        return await asyncio.wait_for(coro, timeout=timeout)

    return asyncio.run(guarded())


async def _alist(server: dict) -> list:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_params(server)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return list((await s.list_tools()).tools)


async def _acall(server: dict, tool: str, args: dict):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(_params(server)) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await s.call_tool(tool, args or {})


def list_tools(root, *, force: bool = False, lister=None) -> list[dict]:
    """[{name, server, tool, decl}] for enabled servers; cached by config mtime."""
    servers, _err = load_servers(root)
    servers = [s for s in servers if s["enabled"]]
    if not servers:
        return []
    p = config_path(root)
    key = (str(p), p.stat().st_mtime if p.exists() else 0)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and not force and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    lister = lister or (lambda srv: _run(_alist(srv), LIST_TIMEOUT))
    out = []
    for srv in servers:
        try:
            tools = lister(srv)
            _last_errors.pop(srv["name"], None)
        except Exception as e:
            _last_errors[srv["name"]] = f"{type(e).__name__}: {str(e)[:120]}"
            continue
        for t in tools[:40]:
            tname = str(getattr(t, "name", "") or "")
            if not tname:
                continue
            desc = str(getattr(t, "description", "") or "")[:400]
            name = decl_name(srv["name"], tname)
            out.append({
                "name": name,
                "server": srv["name"],
                "tool": tname,
                "decl": {
                    "name": name,
                    "description": f"[MCP {srv['name']}; operator must approve (R3)] {desc}".strip(),
                    "parameters": sanitize_schema(_tool_schema(t)),
                },
            })
    with _cache_lock:
        _cache.clear()
        _cache[key] = (time.time(), out)
    return out


def call_tool(root, server_name: str, tool: str, args: dict, *, caller=None) -> dict:
    """Execute one MCP tool call. Only BridgeApi.tool_confirm may call this."""
    servers, _ = load_servers(root)
    srv = next((s for s in servers if s["name"] == server_name and s["enabled"]), None)
    if not srv:
        return {"ok": False, "error": f"MCP server '{server_name}' not configured/enabled"}
    caller = caller or (lambda s, t, a: _run(_acall(s, t, a), CALL_TIMEOUT))
    try:
        res = caller(srv, tool, args or {})
    except Exception as e:
        return {"ok": False, "error": f"MCP call failed: {type(e).__name__}: {str(e)[:200]}"}
    texts = []
    for c in getattr(res, "content", None) or []:
        txt = getattr(c, "text", None)
        texts.append(txt if isinstance(txt, str) else f"[{getattr(c, 'type', 'content')}]")
    is_err = bool(getattr(res, "is_error", getattr(res, "isError", False)))
    text = "\n".join(texts)[:8000]
    return {"ok": not is_err, "data": {"server": server_name, "tool": tool, "text": text}}
