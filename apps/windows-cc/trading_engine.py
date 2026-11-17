# apps/windows-cc/trading_engine.py
"""Trading page data (Phase 3): real indicators from keyless delayed market data + paper ledger.

Signals here are rule-based summaries of indicators (BUY/SELL/NEUTRAL counts), not advice.
Order book depth is not available from a keyless source and is reported as such.
"""
from __future__ import annotations

import json
import re
import time

import indicators
import market_data


def snapshot(symbol: str = "NIFTY", tf: str = "1d", fetch=market_data.fetch) -> dict:
    sym = str(symbol or "NIFTY").upper()
    r = fetch(sym, tf)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error", "market data unavailable"), "source": r.get("source", market_data.SOURCE)}
    bars = r["bars"]
    tech = indicators.technicals(bars)
    daily = r if tf == "1d" else fetch(sym, "1d")
    closes = [b["c"] for b in daily["bars"]] if daily.get("ok") else []
    st = indicators.stats(closes) if closes else {"ok": False, "error": "daily data unavailable"}
    mc = indicators.monte_carlo(closes) if closes else {"ok": False}
    rg = indicators.regime(closes) if closes else {"ok": False}
    wf = indicators.walk_forward(closes) if closes else {"ok": False}
    chg = r["last"] - r["prev_close"]
    overall = tech["summary"]["overall"]
    return {"ok": True, "data": {
        "symbol": sym, "tf": tf, "last": r["last"], "prev_close": r["prev_close"], "change": chg,
        "change_pct": chg / r["prev_close"] * 100 if r["prev_close"] else 0.0,
        "market_time": r["market_time"], "fetched": r["fetched"], "age_s": int(time.time() - r["market_time"]),
        "source": r["source"], "bars": len(bars),
        "spark": [round(b["c"], 2) for b in bars[-60:]],
        "technicals": tech, "stats": st, "monte_carlo": mc, "regime": rg, "walk_forward": wf,
        "signal": {"rating": overall["rating"], "score": overall["score"], "buy": overall["buy"],
                   "sell": overall["sell"], "neutral": overall["neutral"],
                   "basis": f"{overall['buy'] + overall['sell'] + overall['neutral']} indicators on {tf} bars"},
        "order_book": {"available": False, "reason": "Depth needs a broker data feed; the keyless source has none."},
    }}


def headlines_sentiment(symbol: str, root, search=None, complete=None, limit: int = 8) -> dict:
    """Real headlines (DuckDuckGo news, no key) classified by the AI — local model first (cheap task)."""
    q = {"NIFTY": "Nifty 50 stock market India", "BANKNIFTY": "Bank Nifty banking stocks India"}.get(
        str(symbol).upper(), f"{symbol} stock market India")
    try:
        if search:
            rows = search(q, limit)
        else:
            from ddgs import DDGS

            rows = DDGS(timeout=6).news(q, max_results=limit) or []
    except Exception as e:
        return {"ok": False, "error": f"news search failed ({type(e).__name__})"}
    items = [{"title": str(x.get("title") or "")[:200], "url": str(x.get("url") or x.get("href") or ""),
              "source": str(x.get("source") or ""), "date": str(x.get("date") or "")} for x in rows if x.get("title")]
    if not items:
        return {"ok": False, "error": "no headlines found"}
    numbered = "\n".join(f"{i+1}. {it['title']}" for i, it in enumerate(items))
    prompt = ("Classify each headline's likely effect on Indian equity indices as positive, negative or neutral. "
              'Answer ONLY JSON: {"labels": ["positive"|"negative"|"neutral", ...]} in the same order.\n\n' + numbered)
    if complete:
        res = complete(prompt)
    else:
        import llm_router

        res = llm_router.complete(prompt, "You are a terse financial news classifier.", root, cheap=True, max_tokens=200)
    labels: list = []
    if res.get("ok"):
        m = re.search(r"\{.*\}", res["text"], re.S)
        try:
            labels = list((json.loads(m.group(0)) if m else {}).get("labels") or [])
        except Exception:
            labels = []
    for i, it in enumerate(items):
        lab = str(labels[i]).lower() if i < len(labels) else ""
        it["label"] = lab if lab in ("positive", "negative", "neutral") else "unclassified"
    counts = {k: sum(1 for it in items if it["label"] == k) for k in ("positive", "negative", "neutral", "unclassified")}
    scored = counts["positive"] + counts["negative"] + counts["neutral"]
    return {"ok": True, "data": {"items": items, "counts": counts, "provider": res.get("provider", ""),
                                 "score": ((counts["positive"] - counts["negative"]) / scored) if scored else None,
                                 "errors": res.get("errors", [])[:3]}}
