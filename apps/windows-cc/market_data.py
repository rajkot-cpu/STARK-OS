# apps/windows-cc/market_data.py
"""Keyless market data (Phase 3): Yahoo Finance public chart endpoint, no account or API key.

Verified from chandan 2026-11-18 (^NSEI / ^NSEBANK daily + 15m). Unofficial and delayed
(~15 min for NSE indices); Jarvis labels it that way and never fills gaps with made-up numbers.
On failure the caller gets ok=False with the reason — the UI shows "not connected".
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SYMBOLS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN", "FINNIFTY": "NIFTY_FIN_SERVICE.NS"}
# timeframe -> (yahoo interval, range)
TIMEFRAMES = {"5m": ("5m", "5d"), "15m": ("15m", "5d"), "1h": ("60m", "1mo"), "1d": ("1d", "2y"), "1wk": ("1wk", "10y")}
SOURCE = "Yahoo Finance chart API (keyless, unofficial, ~15 min delayed)"
_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
_CACHE: dict = {}
_lock = threading.Lock()
TTL = {"5m": 60, "15m": 90, "1h": 300, "1d": 600, "1wk": 3600}


def fetch(symbol: str = "NIFTY", tf: str = "1d", timeout: float = 10.0, fetch_fn=None) -> dict:
    sym = str(symbol or "NIFTY").upper()
    if sym not in SYMBOLS:
        return {"ok": False, "error": f"unknown symbol {sym}; supported: {', '.join(SYMBOLS)}"}
    if tf not in TIMEFRAMES:
        return {"ok": False, "error": f"unknown timeframe {tf}; supported: {', '.join(TIMEFRAMES)}"}
    key = (sym, tf)
    with _lock:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL[tf]:
            return hit[1]
    interval, rng = TIMEFRAMES[tf]
    q = urllib.parse.quote(SYMBOLS[sym], safe="")
    errors = []
    raw = None
    for host in _HOSTS:
        url = f"https://{host}/v8/finance/chart/{q}?interval={interval}&range={rng}&includePrePost=false"
        try:
            if fetch_fn:
                raw = fetch_fn(url)
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JARVIS market data)"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = json.loads(r.read().decode("utf-8", "replace"))
            break
        except urllib.error.HTTPError as e:
            errors.append(f"{host}: HTTP {e.code}")
        except Exception as e:
            errors.append(f"{host}: {type(e).__name__}")
    if raw is None:
        return {"ok": False, "error": "market data unavailable (" + "; ".join(errors) + ")", "source": SOURCE}
    out = parse(raw, sym, tf)
    if out.get("ok") and tf == "1d":
        # Yahoo's long daily range often lags by a session; the 5-day range has the latest bar.
        try:
            u5 = f"https://{_HOSTS[0]}/v8/finance/chart/{q}?interval=1d&range=5d&includePrePost=false"
            if fetch_fn:
                raw5 = fetch_fn(u5)
            else:
                req = urllib.request.Request(u5, headers={"User-Agent": "Mozilla/5.0 (JARVIS market data)"})
                with urllib.request.urlopen(req, timeout=timeout) as r5:
                    raw5 = json.loads(r5.read().decode("utf-8", "replace"))
            recent = parse(raw5, sym, tf)
            if recent.get("ok"):
                day = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t + 19800))  # IST date
                have = {day(b["t"]) for b in out["bars"]}
                extra = [b for b in recent["bars"] if day(b["t"]) not in have and b["t"] > out["bars"][-1]["t"]]
                if extra:
                    out["bars"] = out["bars"] + extra
                    out["merged_recent"] = len(extra)
        except Exception:
            pass
    if out.get("ok"):
        with _lock:
            _CACHE[key] = (time.time(), out)
    return out


def parse(raw: dict, sym: str, tf: str) -> dict:
    try:
        res = (raw.get("chart") or {}).get("result") or []
        if not res:
            err = (raw.get("chart") or {}).get("error") or {}
            return {"ok": False, "error": f"no data ({err.get('description') or 'empty result'})", "source": SOURCE}
        r = res[0]
        meta = r.get("meta") or {}
        ts = r.get("timestamp") or []
        qd = ((r.get("indicators") or {}).get("quote") or [{}])[0]
        bars = []
        for i, t in enumerate(ts):
            o, h, lo, c = (qd.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close"))
            v = (qd.get("volume") or [None] * len(ts))[i]
            if i == len(ts) - 1 and c is None and o is not None and meta.get("regularMarketPrice") \
                    and int(meta.get("regularMarketTime") or 0) >= int(t):
                # Latest session not yet closed out by Yahoo: use its own session summary (last price,
                # day high/low) for that one bar. Real quote fields, not interpolation.
                c = float(meta["regularMarketPrice"])
                h = max(x for x in (h, meta.get("regularMarketDayHigh"), c, o) if x is not None)
                lo = min(x for x in (lo, meta.get("regularMarketDayLow"), c, o) if x is not None)
            if None in (o, h, lo, c):
                continue  # Yahoo leaves holes for missing bars; skip, never interpolate
            bars.append({"t": int(t), "o": float(o), "h": float(h), "l": float(lo), "c": float(c), "v": float(v or 0)})
        if len(bars) < 2:
            return {"ok": False, "error": "too few bars returned", "source": SOURCE}
        last = float(meta.get("regularMarketPrice") or bars[-1]["c"])
        chg_pct = meta.get("regularMarketChangePercent")
        # previous session close: from Yahoo's own change % when given (chartPreviousClose is the close
        # before the *chart range*, not the previous session), else the prior daily bar.
        prev = last / (1 + float(chg_pct) / 100) if chg_pct not in (None, "") else bars[-2]["c"]
        return {"ok": True, "symbol": sym, "yahoo": meta.get("symbol", ""), "tf": tf, "bars": bars,
                "last": last, "prev_close": float(prev),
                "market_time": int(meta.get("regularMarketTime") or bars[-1]["t"]),
                "exchange_tz": meta.get("exchangeTimezoneName", ""), "source": SOURCE, "fetched": int(time.time())}
    except Exception as e:
        return {"ok": False, "error": f"could not parse market data ({type(e).__name__})", "source": SOURCE}
