# apps/windows-cc/provider_tests.py
"""Read-only "Test connection" checks for keys saved in Settings → Keys & brokers (Phase 3).

Idea adapted from the v8 bundle's api_hub_manager.py (one place to see whether each provider
key works). Differences, on purpose:
  * keys come from Credential Manager / environment, never a plaintext .env, and no part of a
    key is ever returned (v8 returned first4...last4 masks);
  * every check is a fixed, read-only GET to the provider's own host (account/profile/quote) —
    never an order endpoint, and no free-form URL (v8's custom REST tester could call any URL);
  * results carry only status, HTTP code, latency and a short non-secret detail.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "JARVIS/3.1 (+provider check)"
TESTS = ("gemini", "openai", "groq", "anthropic", "tavily", "brave", "serper", "serpapi", "finnhub", "alphavantage", "kite", "alpaca", "binance")
_AI = {"gemini": ("Gemini", "JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
       "openai": ("OpenAI", "JARVIS_OPENAI_API_KEY", ("OPENAI_API_KEY",)),
       "groq": ("Groq", "JARVIS_GROQ_API_KEY", ("GROQ_API_KEY",)),
       "anthropic": ("Anthropic", "JARVIS_ANTHROPIC_API_KEY", ("ANTHROPIC_API_KEY",))}


def _k(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _get(url: str, headers: dict, timeout: float = 8.0) -> tuple[int | None, dict | None, float]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(65536).decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        return e.code, None, round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        return None, None, round((time.perf_counter() - t0) * 1000, 1)
    try:
        data = json.loads(body)
    except Exception:
        data = None
    return code, data, round((time.perf_counter() - t0) * 1000, 1)


def _result(code, ms, ok_detail="", data_ok=True) -> dict:
    if code is None:
        return {"ok": False, "status": "network_error", "latency_ms": ms, "detail": "provider unreachable"}
    if code in (401, 403):
        return {"ok": False, "status": "auth_error", "http": code, "latency_ms": ms, "detail": "key rejected"}
    if code == 200 and data_ok:
        return {"ok": True, "status": "connected", "http": code, "latency_ms": ms, "detail": ok_detail}
    return {"ok": False, "status": "error", "http": code, "latency_ms": ms, "detail": ok_detail or f"HTTP {code}"}


def run(provider: str, root=None, get=_get) -> dict:
    p = str(provider or "").lower().strip()
    if p not in TESTS:
        return {"ok": False, "status": "unsupported", "detail": f"no read-only test for '{p}'"}
    try:
        from llm_providers import load_secrets

        load_secrets(root)
    except Exception:
        pass
    if p in _AI:
        from llm_providers import probe_one

        name, env, aliases = _AI[p]
        t0 = time.perf_counter()
        r = probe_one(p, name, env, 8.0, aliases=aliases)
        st = r.get("state", "")
        return {"ok": st == "connected", "status": st, "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "detail": "models list reachable" if st == "connected" else ("key not set" if st == "missing_key" else st)}
    if p in ("tavily", "brave", "serper", "serpapi"):
        import web_search

        env = dict(web_search.KEYED)[p]
        k = _k(env)
        if not k:
            return {"ok": False, "status": "missing_key", "detail": f"{env} not set"}
        if p == "serpapi":  # account endpoint: free, uses no search credit
            code, d, ms = get("https://serpapi.com/account.json?api_key=" + urllib.parse.quote(k), {})
            return _result(code, ms, "account read OK", bool(d and ("account_email" in d or "plan_id" in d
                                                                     or "searches_per_month" in d)))
        t0 = time.perf_counter()
        try:
            rows = web_search._KEYED_FN[p]("JARVIS connection test", 1, k)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            return {"ok": True, "status": "connected", "latency_ms": ms,
                    "detail": f"search OK ({len(rows)} result; uses 1 query credit)"}
        except Exception as e:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            msg = str(e)[:60]
            st = "auth_error" if ("401" in msg or "403" in msg) else "error"
            return {"ok": False, "status": st, "latency_ms": ms, "detail": msg}
    if p == "finnhub":
        k = _k("JARVIS_FINNHUB_API_KEY")
        if not k:
            return {"ok": False, "status": "missing_key", "detail": "JARVIS_FINNHUB_API_KEY not set"}
        code, d, ms = get("https://finnhub.io/api/v1/quote?symbol=AAPL", {"X-Finnhub-Token": k})
        return _result(code, ms, "quote endpoint OK (AAPL)", bool(d and d.get("c") is not None))
    if p == "alphavantage":
        k = _k("JARVIS_ALPHAVANTAGE_API_KEY")
        if not k:
            return {"ok": False, "status": "missing_key", "detail": "JARVIS_ALPHAVANTAGE_API_KEY not set"}
        # Alpha Vantage only accepts the key as a query parameter; this URL is never logged.
        code, d, ms = get("https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey="
                          + urllib.parse.quote(k), {})
        good = bool(d and "Global Quote" in d)
        note = "quote endpoint OK (IBM)" if good else str((d or {}).get("Note") or (d or {}).get("Information")
                                                          or (d or {}).get("Error Message") or "unexpected reply")[:120]
        return _result(code, ms, note, good)
    if p == "kite":
        ak, at = _k("JARVIS_BROKER_KITE_API_KEY"), _k("JARVIS_BROKER_KITE_ACCESS_TOKEN")
        if not (ak and at):
            return {"ok": False, "status": "missing_key", "detail": "Kite API key and access token both needed"}
        code, d, ms = get("https://api.kite.trade/user/profile", {"X-Kite-Version": "3", "Authorization": f"token {ak}:{at}"})
        return _result(code, ms, "profile read OK (read-only)", bool(d and d.get("status") == "success"))
    if p == "alpaca":
        ak, sk = _k("JARVIS_BROKER_ALPACA_API_KEY"), _k("JARVIS_BROKER_ALPACA_SECRET_KEY")
        if not (ak and sk):
            return {"ok": False, "status": "missing_key", "detail": "Alpaca key ID and secret both needed"}
        code, d, ms = get("https://paper-api.alpaca.markets/v2/account", {"APCA-API-KEY-ID": ak, "APCA-API-SECRET-KEY": sk})
        return _result(code, ms, "paper account read OK", bool(d and d.get("status")))
    if p == "binance":
        ak, sk = _k("JARVIS_BROKER_BINANCE_API_KEY"), _k("JARVIS_BROKER_BINANCE_API_SECRET")
        if not (ak and sk):
            return {"ok": False, "status": "missing_key", "detail": "Binance API key and secret both needed"}
        qs = f"timestamp={int(time.time() * 1000)}&recvWindow=10000"
        sig = hmac.new(sk.encode(), qs.encode(), hashlib.sha256).hexdigest()
        code, d, ms = get(f"https://api.binance.com/api/v3/account?{qs}&signature={sig}", {"X-MBX-APIKEY": ak})
        return _result(code, ms, "account read OK (read-only)", bool(d and "balances" in d))
    return {"ok": False, "status": "unsupported"}
