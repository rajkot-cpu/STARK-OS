# apps/windows-cc/keys_manager.py
"""Add / replace / remove provider and broker keys from Settings (Phase 3).

Values go straight into Windows Credential Manager (JARVIS/<NAME>) and are never returned,
logged or audited — only the key NAME and whether it is set. Custom names are remembered in
config/key_names.json (names only) so they load at start-up.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import secrets_store

NAME_RE = re.compile(r"^JARVIS_[A-Z0-9_]{2,60}$")
RESERVED = {"JARVIS_API_TOKEN"}  # managed by the local API (rotate only)
# "test" names a read-only connection check in provider_tests.py (never an order).
SLOTS = (
    {"name": "JARVIS_GEMINI_API_KEY", "label": "Google Gemini", "group": "AI provider", "used": True, "test": "gemini"},
    {"name": "JARVIS_OPENAI_API_KEY", "label": "OpenAI", "group": "AI provider", "used": True, "test": "openai"},
    {"name": "JARVIS_GROQ_API_KEY", "label": "Groq", "group": "AI provider", "used": True, "test": "groq"},
    {"name": "JARVIS_ANTHROPIC_API_KEY", "label": "Anthropic", "group": "AI provider", "used": False, "test": "anthropic"},
    {"name": "JARVIS_OPENROUTER_API_KEY", "label": "OpenRouter", "group": "AI provider", "used": False, "test": ""},
    {"name": "JARVIS_TAVILY_API_KEY", "label": "Tavily search", "group": "Web search", "used": True, "test": "tavily"},
    {"name": "JARVIS_BRAVE_SEARCH_API_KEY", "label": "Brave Search API", "group": "Web search", "used": True, "test": "brave"},
    {"name": "JARVIS_SERPER_API_KEY", "label": "Serper (Google)", "group": "Web search", "used": True, "test": "serper"},
    {"name": "JARVIS_SERPAPI_API_KEY", "label": "SerpAPI (Google)", "group": "Web search", "used": True, "test": "serpapi"},
    {"name": "JARVIS_FINNHUB_API_KEY", "label": "Finnhub", "group": "Market data", "used": False, "test": "finnhub"},
    {"name": "JARVIS_ALPHAVANTAGE_API_KEY", "label": "Alpha Vantage", "group": "Market data", "used": False, "test": "alphavantage"},
    {"name": "JARVIS_BROKER_SAHI_API_KEY", "label": "Sahi — API key", "group": "Broker", "used": False, "test": ""},
    {"name": "JARVIS_BROKER_SAHI_API_SECRET", "label": "Sahi — API secret", "group": "Broker", "used": False, "test": ""},
    {"name": "JARVIS_BROKER_KITE_API_KEY", "label": "Zerodha Kite — API key", "group": "Broker", "used": False, "test": "kite"},
    {"name": "JARVIS_BROKER_KITE_ACCESS_TOKEN", "label": "Zerodha Kite — access token", "group": "Broker", "used": False, "test": "kite"},
    {"name": "JARVIS_BROKER_ALPACA_API_KEY", "label": "Alpaca (paper) — key ID", "group": "Broker", "used": False, "test": "alpaca"},
    {"name": "JARVIS_BROKER_ALPACA_SECRET_KEY", "label": "Alpaca (paper) — secret", "group": "Broker", "used": False, "test": "alpaca"},
    {"name": "JARVIS_BROKER_BINANCE_API_KEY", "label": "Binance — API key", "group": "Broker", "used": False, "test": "binance"},
    {"name": "JARVIS_BROKER_BINANCE_API_SECRET", "label": "Binance — API secret", "group": "Broker", "used": False, "test": "binance"},
    {"name": "JARVIS_BROKER_OTHER_API_KEY", "label": "Other broker — API key", "group": "Broker", "used": False, "test": ""},
    {"name": "JARVIS_BROKER_OTHER_API_SECRET", "label": "Other broker — API secret", "group": "Broker", "used": False, "test": ""},
)


def _names_file(root) -> Path:
    return Path(root) / "config" / "key_names.json"


def custom_names(root) -> list[str]:
    try:
        raw = json.loads(_names_file(root).read_text(encoding="utf-8"))
        return [n for n in raw if isinstance(n, str) and NAME_RE.match(n)]
    except Exception:
        return []


def all_names(root) -> list[str]:
    return list(dict.fromkeys([s["name"] for s in SLOTS] + custom_names(root)))


def _remember(root, name: str, add: bool = True) -> None:
    names = custom_names(root)
    if add and name not in names and name not in {s["name"] for s in SLOTS}:
        names.append(name)
    if not add and name in names:
        names.remove(name)
    p = _names_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(names, indent=2), encoding="utf-8")


def where(name: str, root) -> str:
    if secrets_store.available() and secrets_store.read(name):
        return "credential_manager"
    try:
        if any(k == name for k, _ in secrets_store.parse_env(secrets_store.env_path(root))):
            return "api_keys.env"
    except Exception:
        pass
    if os.environ.get(name, "").strip():
        return "environment"
    return ""


def status(root) -> dict:
    rows = []
    slot_names = {s["name"] for s in SLOTS}
    for s in SLOTS:
        w = where(s["name"], root)
        rows.append({**s, "set": bool(w), "where": w, "custom": False})
    for n in custom_names(root):
        if n in slot_names:
            continue
        w = where(n, root)
        rows.append({"name": n, "label": n.replace("JARVIS_", "").replace("_", " ").title(), "group": "Custom",
                     "used": False, "test": "", "set": bool(w), "where": w, "custom": True})
    return {"credential_manager": secrets_store.available(), "keys": rows}


def set_key(root, name: str, value: str) -> dict:
    name = str(name or "").strip().upper()
    value = str(value or "").strip()
    if not NAME_RE.match(name) or name in RESERVED:
        return {"ok": False, "error": "name must look like JARVIS_SOMETHING_API_KEY (A-Z, 0-9, _)"}
    if not (8 <= len(value) <= 4096) or any(ch in value for ch in "\r\n\t "):
        return {"ok": False, "error": "value must be 8-4096 characters with no spaces or line breaks"}
    if not secrets_store.available():
        return {"ok": False, "error": "Windows Credential Manager is not available on this machine"}
    if not secrets_store.write(name, value) or secrets_store.read(name) != value:
        return {"ok": False, "error": "Credential Manager write could not be verified"}
    os.environ[name] = value  # takes effect now; never echoed back
    _remember(root, name, True)
    try:
        from llm_providers import clear_cached_probes

        clear_cached_probes()
    except Exception:
        pass
    _audit(root, "key_set", f"{name} stored in Credential Manager (value not logged)")
    return {"ok": True, "data": {"name": name, "set": True, "where": "credential_manager"}}


def delete_key(root, name: str, confirmed: bool = False) -> dict:
    name = str(name or "").strip().upper()
    if not NAME_RE.match(name) or name in RESERVED:
        return {"ok": False, "error": "bad key name"}
    if confirmed is not True:
        return {"ok": False, "error": "confirmation required to remove a key"}
    ok = secrets_store.delete(name) if secrets_store.available() else False
    os.environ.pop(name, None)
    _remember(root, name, False)
    _audit(root, "key_delete", f"{name} removed from Credential Manager" + ("" if ok else " (was not stored there)"))
    return {"ok": True, "data": {"name": name, "set": bool(where(name, root))}}


def _audit(root, action: str, result: str) -> None:
    try:
        from cc_settings import audit

        audit(root, "keys", action, result)
    except Exception:
        pass
