# apps/windows-cc/indicators.py
"""Technical indicators + statistics computed from real OHLC bars (Phase 3). Pure Python.

Every number shown on the Trading page comes from here, from bars fetched by market_data.
Rules follow common textbook definitions (Wilder RSI/ATR/ADX, 12-26-9 MACD, 14-3-3 Stochastic,
20 CCI, 14 Williams %R). Statistics are descriptive of the past, not a forecast.
"""
from __future__ import annotations

import math
import random


# ---- moving averages ----
def sma(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(xs[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(xs)):
        prev = xs[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _wilder(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    prev = sum(xs[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(xs)):
        prev = (prev * (n - 1) + xs[i]) / n
        out[i] = prev
    return out


# ---- oscillators ----
def rsi(c: list[float], n: int = 14) -> float | None:
    if len(c) <= n:
        return None
    gains = [max(0.0, c[i] - c[i - 1]) for i in range(1, len(c))]
    losses = [max(0.0, c[i - 1] - c[i]) for i in range(1, len(c))]
    ag, al = _wilder(gains, n)[-1], _wilder(losses, n)[-1]
    if ag is None or al is None:
        return None
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def macd(c: list[float], fast: int = 12, slow: int = 26, sig: int = 9) -> dict | None:
    if len(c) < slow + sig:
        return None
    ef, es = ema(c, fast), ema(c, slow)
    line = [f - s for f, s in zip(ef, es) if f is not None and s is not None]
    sl = ema(line, sig)
    if sl[-1] is None:
        return None
    return {"macd": line[-1], "signal": sl[-1], "hist": line[-1] - sl[-1]}


def stochastic(h, lo, c, n: int = 14, k_smooth: int = 3, d_smooth: int = 3) -> dict | None:
    if len(c) < n + k_smooth + d_smooth:
        return None
    raw = []
    for i in range(n - 1, len(c)):
        hh, ll = max(h[i - n + 1:i + 1]), min(lo[i - n + 1:i + 1])
        raw.append(50.0 if hh == ll else 100.0 * (c[i] - ll) / (hh - ll))
    k = [x for x in sma(raw, k_smooth) if x is not None]
    d = [x for x in sma(k, d_smooth) if x is not None]
    return {"k": k[-1], "d": d[-1]} if k and d else None


def cci(h, lo, c, n: int = 20) -> float | None:
    if len(c) < n:
        return None
    tp = [(a + b + x) / 3 for a, b, x in zip(h, lo, c)]
    w = tp[-n:]
    m = sum(w) / n
    md = sum(abs(x - m) for x in w) / n
    return 0.0 if md == 0 else (tp[-1] - m) / (0.015 * md)


def williams_r(h, lo, c, n: int = 14) -> float | None:
    if len(c) < n:
        return None
    hh, ll = max(h[-n:]), min(lo[-n:])
    return -50.0 if hh == ll else -100.0 * (hh - c[-1]) / (hh - ll)


def momentum(c, n: int = 10) -> float | None:
    return c[-1] - c[-1 - n] if len(c) > n else None


def atr(h, lo, c, n: int = 14) -> float | None:
    if len(c) <= n:
        return None
    tr = [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))]
    return _wilder(tr, n)[-1]


def adx(h, lo, c, n: int = 14) -> dict | None:
    if len(c) < 2 * n + 1:
        return None
    tr, pdm, mdm = [], [], []
    for i in range(1, len(c)):
        up, dn = h[i] - h[i - 1], lo[i - 1] - lo[i]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])))
    atr_s, p_s, m_s = _wilder(tr, n), _wilder(pdm, n), _wilder(mdm, n)
    dx = []
    pdi = mdi = 0.0
    for a, p, m in zip(atr_s, p_s, m_s):
        if a is None or a == 0:
            continue
        pdi, mdi = 100 * p / a, 100 * m / a
        dx.append(0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi))
    ad = _wilder(dx, n)[-1] if len(dx) >= n else None
    return None if ad is None else {"adx": ad, "plus_di": pdi, "minus_di": mdi}


# ---- pivots (from the previous completed bar's H/L/C/O) ----
def pivots(o: float, h: float, lo: float, c: float) -> dict:
    p = (h + lo + c) / 3
    r = h - lo
    classic = {"S3": lo - 2 * (h - p), "S2": p - r, "S1": 2 * p - h, "P": p, "R1": 2 * p - lo, "R2": p + r, "R3": h + 2 * (p - lo)}
    fib = {"S3": p - r, "S2": p - 0.618 * r, "S1": p - 0.382 * r, "P": p, "R1": p + 0.382 * r, "R2": p + 0.618 * r, "R3": p + r}
    cam = {"S3": c - r * 1.1 / 4, "S2": c - r * 1.1 / 6, "S1": c - r * 1.1 / 12, "P": p,
           "R1": c + r * 1.1 / 12, "R2": c + r * 1.1 / 6, "R3": c + r * 1.1 / 4}
    wp = (h + lo + 2 * c) / 4
    woodie = {"S3": lo - 2 * (h - wp), "S2": wp - r, "S1": 2 * wp - h, "P": wp, "R1": 2 * wp - lo, "R2": wp + r, "R3": h + 2 * (wp - lo)}
    x = (h + 2 * lo + c) if c < o else ((2 * h + lo + c) if c > o else (h + lo + 2 * c))
    demark = {"S1": x / 2 - h, "P": x / 4, "R1": x / 2 - lo}
    return {"classic": classic, "fibonacci": fib, "camarilla": cam, "woodie": woodie, "demark": demark}


# ---- ratings ----
def _vote(v: int) -> str:
    return "BUY" if v > 0 else ("SELL" if v < 0 else "NEUTRAL")


def _rating(score: float) -> str:
    if score >= 0.5:
        return "STRONG BUY"
    if score >= 0.1:
        return "BUY"
    if score <= -0.5:
        return "STRONG SELL"
    if score <= -0.1:
        return "SELL"
    return "NEUTRAL"


def technicals(bars: list[dict]) -> dict:
    o = [b["o"] for b in bars]
    h = [b["h"] for b in bars]
    lo = [b["l"] for b in bars]
    c = [b["c"] for b in bars]
    price = c[-1]
    osc = []
    r = rsi(c)
    if r is not None:
        osc.append({"name": "RSI (14)", "value": r, "action": _vote(1 if r < 30 else (-1 if r > 70 else 0))})
    st = stochastic(h, lo, c)
    if st:
        v = 1 if st["k"] < 20 and st["k"] > st["d"] else (-1 if st["k"] > 80 and st["k"] < st["d"] else 0)
        osc.append({"name": "Stochastic %K (14,3,3)", "value": st["k"], "action": _vote(v)})
    cc = cci(h, lo, c)
    if cc is not None:
        osc.append({"name": "CCI (20)", "value": cc, "action": _vote(1 if cc < -100 else (-1 if cc > 100 else 0))})
    ad = adx(h, lo, c)
    if ad:
        v = 0 if ad["adx"] < 20 else (1 if ad["plus_di"] > ad["minus_di"] else -1)
        osc.append({"name": "ADX (14)", "value": ad["adx"], "action": _vote(v)})
    wr = williams_r(h, lo, c)
    if wr is not None:
        osc.append({"name": "Williams %R (14)", "value": wr, "action": _vote(1 if wr < -80 else (-1 if wr > -20 else 0))})
    mo = momentum(c)
    if mo is not None:
        osc.append({"name": "Momentum (10)", "value": mo, "action": _vote(1 if mo > 0 else (-1 if mo < 0 else 0))})
    md = macd(c)
    if md:
        osc.append({"name": "MACD (12,26,9)", "value": md["macd"], "signal": md["signal"], "hist": md["hist"],
                    "action": _vote(1 if md["macd"] > md["signal"] else -1)})
    mas = []
    for n in (10, 20, 50, 100, 200):
        for kind, fn in (("EMA", ema), ("SMA", sma)):
            v = fn(c, n)[-1]
            if v is not None:
                mas.append({"name": f"{kind} ({n})", "value": v, "action": _vote(1 if price > v else (-1 if price < v else 0))})

    def summ(rows):
        b = sum(1 for x in rows if x["action"] == "BUY")
        s = sum(1 for x in rows if x["action"] == "SELL")
        n = len(rows)
        score = (b - s) / n if n else 0.0
        return {"buy": b, "sell": s, "neutral": n - b - s, "score": score, "rating": _rating(score) if n else "N/A"}

    so, sm = summ(osc), summ(mas)
    allr = summ(osc + mas)
    prev = bars[-2]
    return {"price": price, "oscillators": osc, "moving_averages": mas,
            "summary": {"oscillators": so, "moving_averages": sm, "overall": allr},
            "atr": atr(h, lo, c), "pivots": pivots(prev["o"], prev["h"], prev["l"], prev["c"]),
            "pivots_from": prev["t"], "bars": len(bars)}


# ---- statistics (descriptive, from real returns) ----
def returns(c: list[float]) -> list[float]:
    return [c[i] / c[i - 1] - 1 for i in range(1, len(c)) if c[i - 1]]


def _sharpe(rs: list[float], periods: int) -> float:
    if len(rs) < 2:
        return 0.0
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
    return 0.0 if sd == 0 else m / sd * math.sqrt(periods)


def stats(c: list[float], periods: int = 252, seed: int = 7, boots: int = 500) -> dict:
    rs = returns(c)
    n = len(rs)
    if n < 30:
        return {"ok": False, "error": "need at least 30 returns"}
    m = sum(rs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (n - 1))
    sh = _sharpe(rs, periods)
    rng = random.Random(seed)
    bs = sorted(_sharpe([rs[rng.randrange(n)] for _ in range(n)], periods) for _ in range(boots))
    t = 0.0 if sd == 0 else m / (sd / math.sqrt(n))
    p = math.erfc(abs(t) / math.sqrt(2))  # two-sided, normal approximation
    peak, mdd = c[0], 0.0
    for x in c:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1)
    srt = sorted(rs)
    k = max(1, int(0.05 * n))
    return {"ok": True, "n": n, "mean": m, "vol_annual": sd * math.sqrt(periods), "sharpe": sh,
            "sharpe_ci95": [bs[int(0.025 * boots)], bs[int(0.975 * boots) - 1]], "t_stat": t, "p_value": p,
            "max_drawdown": mdd, "var95": -srt[k - 1], "cvar95": -sum(srt[:k]) / k,
            "win_rate": sum(1 for x in rs if x > 0) / n}


def monte_carlo(c: list[float], horizon: int = 20, paths: int = 1000, seed: int = 11) -> dict:
    """Bootstrap past returns into future paths. Shows the spread of history, not a prediction."""
    rs = returns(c)
    if len(rs) < 30:
        return {"ok": False, "error": "need at least 30 returns"}
    rng = random.Random(seed)
    finals = []
    for _ in range(paths):
        v = c[-1]
        for _ in range(horizon):
            v *= 1 + rs[rng.randrange(len(rs))]
        finals.append(v)
    finals.sort()

    def pct(q):
        return finals[min(len(finals) - 1, int(q * len(finals)))]

    return {"ok": True, "horizon": horizon, "paths": paths, "start": c[-1],
            "p5": pct(0.05), "p25": pct(0.25), "p50": pct(0.5), "p75": pct(0.75), "p95": pct(0.95),
            "prob_up": sum(1 for x in finals if x > c[-1]) / paths}


def regime(c: list[float], band: float | None = None) -> dict:
    """3-state Markov chain on daily returns (Bear / Sideways / Bull) with its transition matrix."""
    rs = returns(c)
    if len(rs) < 40:
        return {"ok": False, "error": "need at least 40 returns"}
    if band is None:
        m = sum(rs) / len(rs)
        band = 0.5 * math.sqrt(sum((x - m) ** 2 for x in rs) / (len(rs) - 1))
    names = ["Bear", "Sideways", "Bull"]
    st = [0 if r < -band else (2 if r > band else 1) for r in rs]
    cnt = [[0] * 3 for _ in range(3)]
    for a, b in zip(st, st[1:]):
        cnt[a][b] += 1
    mat = [[(x / sum(row)) if sum(row) else 0.0 for x in row] for row in cnt]
    # 20-bar trend regime (slope of SMA20 vs SMA50) for the headline label
    s20, s50 = sma(c, 20)[-1], sma(c, 50)[-1]
    trend = "N/A" if s20 is None or s50 is None else ("Bull" if s20 > s50 * 1.002 else ("Bear" if s20 < s50 * 0.998 else "Sideways"))
    cur = st[-1]
    return {"ok": True, "states": names, "band": band, "matrix": mat, "counts": cnt, "current": names[cur],
            "next": {names[j]: mat[cur][j] for j in range(3)}, "trend": trend,
            "occupancy": {names[i]: st.count(i) / len(st) for i in range(3)}}


def _ema_cross_returns(c: list[float], fast: int, slow: int, start: int, end: int) -> list[float]:
    ef, es = ema(c, fast), ema(c, slow)
    out = []
    for i in range(max(start, 1), end):
        f, s = ef[i - 1], es[i - 1]
        pos = 1.0 if (f is not None and s is not None and f > s) else 0.0  # long/flat, decided on the prior bar
        out.append(pos * (c[i] / c[i - 1] - 1))
    return out


def walk_forward(c: list[float], folds: int = 5, periods: int = 252) -> dict:
    """Anchored walk-forward of a long/flat EMA-crossover rule: pick (fast, slow) on the train
    window by Sharpe, then score it on the next unseen window. Honest out-of-sample numbers."""
    grid = [(f, s) for f in (5, 10, 20) for s in (30, 50, 100) if f < s]
    n = len(c)
    if n < 300:
        return {"ok": False, "error": "need at least 300 bars (use the daily timeframe)"}
    first_test = int(n * 0.4)
    size = (n - first_test) // folds
    rows = []
    oos_all: list[float] = []
    for k in range(folds):
        a, b = first_test + k * size, (first_test + (k + 1) * size) if k < folds - 1 else n
        best = max(grid, key=lambda g: _sharpe(_ema_cross_returns(c, g[0], g[1], 101, a), periods))
        is_sh = _sharpe(_ema_cross_returns(c, best[0], best[1], 101, a), periods)
        oos = _ema_cross_returns(c, best[0], best[1], a, b)
        bh = [c[i] / c[i - 1] - 1 for i in range(a, b)]
        oos_all += oos
        rows.append({"fold": k + 1, "train_bars": a, "test_bars": b - a, "fast": best[0], "slow": best[1],
                     "is_sharpe": is_sh, "oos_sharpe": _sharpe(oos, periods),
                     "oos_return": math.prod(1 + x for x in oos) - 1, "buy_hold_return": math.prod(1 + x for x in bh) - 1})
    return {"ok": True, "rule": "EMA fast/slow crossover, long or flat", "folds": rows,
            "oos_sharpe": _sharpe(oos_all, periods), "oos_return": math.prod(1 + x for x in oos_all) - 1}
