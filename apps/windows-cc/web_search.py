# apps/windows-cc/web_search.py
"""Read-only web search for agents (R1) with a multi-source fallback chain (Phase 3b).

Order (first that returns results wins; later sources top up until max_results):
  1. keyed APIs, only if a key is saved in Credential Manager:
     Tavily, Brave Search, Serper (Google), SerpAPI (Google)
  2. ddgs package (DuckDuckGo metasearch; backends yahoo → bing)
  3. Bing web RSS            (keyless, https://www.bing.com/search?format=rss)
  4. Google News RSS         (keyless; moved before Bing for news/market queries)
  5. DuckDuckGo HTML         (keyless, html.duckduckgo.com)
  6. Wikipedia (MediaWiki)   (keyless API)
  7. Gemini google_search grounding (only if everything above returned nothing)

Each source has its own timeout and one retry with backoff on network/5xx/429 errors. Results are
deduplicated by normalised URL and always carry the real source URL and which engine found it.
Nothing is ever made up: if every source fails the call returns ok=False with each source's error.
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DDGS_TIMEOUT = 5
SOURCE_TIMEOUT = 8.0          # per source attempt
OVERALL_TIMEOUT = 30.0        # whole chain
RETRIES = 1
BACKOFF = 0.8
# Measured on chandan 2026-11-18: ddgs yahoo/bing/google OK; auto/duckduckgo/brave/mojeek "No results".
# "google" is deliberately NOT used: scraping Google from the operator's IP got that IP a Google
# "unusual traffic" captcha in his own browser.
BACKENDS = ("yahoo", "bing")
GROUNDING_MODEL = "gemini-3.1-flash-lite-preview"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
KEYED = (  # (engine, Credential Manager name)
    ("tavily", "JARVIS_TAVILY_API_KEY"),
    ("brave", "JARVIS_BRAVE_SEARCH_API_KEY"),
    ("serper", "JARVIS_SERPER_API_KEY"),
    ("serpapi", "JARVIS_SERPAPI_API_KEY"),
)
NEWSY = re.compile(r"\b(news|latest|today|this week|outlook|update|breaking|price|market|stocks?|nifty|sensex|"
                   r"election|results?|forecast|20\d\d)\b", re.I)
# Engines whose ranking ignores part of the query; their hits go through relevant().
LOOSE = {"bing", "duckduckgo_html", "wikipedia"}
_TAG = re.compile(r"<[^>]+>")


class Retryable(RuntimeError):
    pass


def _clean(s, n=300) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", str(s or ""))).split())[:n]


def _row(title, url, snippet, source) -> dict | None:
    url = str(url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    return {"title": _clean(title, 160) or url[:160], "url": url[:400], "snippet": _clean(snippet), "source": source}


def _http(url: str, *, data: dict | None = None, headers: dict | None = None, timeout: float = SOURCE_TIMEOUT) -> bytes:
    h = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9", **(headers or {})}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(2_000_000)
    except urllib.error.HTTPError as e:
        if e.code == 429 or e.code >= 500:
            raise Retryable(f"HTTP {e.code}") from None
        raise RuntimeError(f"HTTP {e.code}") from None  # never echo the URL (may hold a key)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Retryable(f"unreachable ({type(e).__name__})") from None


# ---------- keyless sources ----------
def _ddgs(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    rows, last = [], None
    for be in BACKENDS:
        try:
            rows = DDGS(timeout=DDGS_TIMEOUT).text(query, max_results=max_results, backend=be)
        except Exception as e:  # "No results found" / timeouts per backend
            last = e
            continue
        if rows:
            break
    if not rows and last is not None:
        raise last
    out = [_row(r.get("title"), r.get("href") or r.get("url"), r.get("body"), "ddgs") for r in rows or []]
    return [r for r in out if r]


def _rss(raw: bytes, source: str, n: int) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        desc = it.findtext("description") or ""
        pub = it.findtext("source") or ""
        date = it.findtext("pubDate") or ""
        if source == "google_news":
            desc = " · ".join(x for x in (pub, date[:16]) if x)
        r = _row(title, link, desc, source)
        if r:
            out.append(r)
        if len(out) >= n:
            break
    return out


def _bing_rss(query: str, n: int) -> list[dict]:
    q = urllib.parse.quote(query)
    return _rss(_http(f"https://www.bing.com/search?format=rss&setlang=en-IN&q={q}"), "bing", n)


def _google_news(query: str, n: int) -> list[dict]:
    q = urllib.parse.quote(query)
    return _rss(_http(f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"), "google_news", n)


_DDG_A = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_DDG_S = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)


def _ddg_html(query: str, n: int) -> list[dict]:
    raw = _http("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)).decode("utf-8", "replace")
    links, snips, out = _DDG_A.findall(raw), _DDG_S.findall(raw), []
    for i, (href, title) in enumerate(links):
        href = html.unescape(href)
        if href.startswith("//"):
            href = "https:" + href
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if "uddg" in qs:
            href = qs["uddg"][0]
        if "duckduckgo.com/y.js" in href or "ad_domain" in href:
            continue  # ads
        r = _row(title, href, snips[i] if i < len(snips) else "", "duckduckgo_html")
        if r:
            out.append(r)
        if len(out) >= n:
            break
    return out


def _wikipedia(query: str, n: int) -> list[dict]:
    q = urllib.parse.quote(query)
    d = json.loads(_http("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json"
                         f"&utf8=1&srlimit={int(n)}&srsearch={q}"))
    out = []
    for s in (d.get("query") or {}).get("search") or []:
        t = s.get("title") or ""
        r = _row(t, "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_")), s.get("snippet"),
                 "wikipedia")
        if r:
            out.append(r)
    return out


# ---------- keyed sources (key from Credential Manager via environment) ----------
def _tavily(query, n, key):
    d = json.loads(_http("https://api.tavily.com/search", data={"query": query, "max_results": int(n)},
                         headers={"Authorization": f"Bearer {key}"}))
    return [r for r in (_row(x.get("title"), x.get("url"), x.get("content"), "tavily") for x in d.get("results") or []) if r]


def _brave(query, n, key):
    d = json.loads(_http("https://api.search.brave.com/res/v1/web/search?count=%d&q=%s" % (int(n), urllib.parse.quote(query)),
                         headers={"X-Subscription-Token": key, "Accept": "application/json"}))
    rows = ((d.get("web") or {}).get("results")) or []
    return [r for r in (_row(x.get("title"), x.get("url"), x.get("description"), "brave") for x in rows) if r]


def _serper(query, n, key):
    d = json.loads(_http("https://google.serper.dev/search", data={"q": query, "num": int(n), "gl": "in"},
                         headers={"X-API-KEY": key}))
    return [r for r in (_row(x.get("title"), x.get("link"), x.get("snippet"), "serper") for x in d.get("organic") or []) if r]


def _serpapi(query, n, key):
    # SerpAPI only accepts the key as a query parameter; this URL is never logged or echoed.
    d = json.loads(_http("https://serpapi.com/search.json?engine=google&gl=in&num=%d&q=%s&api_key=%s"
                         % (int(n), urllib.parse.quote(query), urllib.parse.quote(key))))
    return [r for r in (_row(x.get("title"), x.get("link"), x.get("snippet"), "serpapi")
                        for x in d.get("organic_results") or []) if r]


_KEYED_FN = {"tavily": _tavily, "brave": _brave, "serper": _serper, "serpapi": _serpapi}


def default_chain(query: str, keys: dict | None = None) -> list[tuple[str, object]]:
    """Ordered [(engine, fn(q, n))]. keys: {engine: key}; default reads JARVIS_* from the environment."""
    if keys is None:
        keys = {e: (os.environ.get(env) or "").strip() for e, env in KEYED}
    chain = [(e, (lambda q, n, _f=_KEYED_FN[e], _k=k: _f(q, n, _k))) for e, k in keys.items() if k and e in _KEYED_FN]
    chain.append(("ddgs", _ddgs))
    if NEWSY.search(query or ""):  # news/market topics: fresh articles before generic pages
        chain += [("google_news", _google_news), ("bing", _bing_rss), ("duckduckgo_html", _ddg_html), ("wikipedia", _wikipedia)]
    else:
        chain += [("bing", _bing_rss), ("duckduckgo_html", _ddg_html), ("wikipedia", _wikipedia), ("google_news", _google_news)]
    return chain


def chain_names(query: str = "") -> list[str]:
    return [n for n, _ in default_chain(query)]


# ---------- helpers ----------
def _with_timeout(fn, timeout: float):
    box: dict = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(max(0.05, timeout))
    if t.is_alive():
        raise TimeoutError(f"timed out after {timeout:.0f}s")
    if "e" in box:
        raise box["e"]
    return box.get("v")


_STOP = {"the", "and", "for", "with", "this", "that", "what", "how", "why", "who", "are", "was", "from", "about",
         "into", "over", "near", "than", "then", "will", "does", "did", "its", "you", "your", "our", "today", "latest",
         "news", "week", "month", "year"}


def _terms(q: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", q.lower())
    return list(dict.fromkeys(t for t in toks if t not in _STOP and (len(t) >= 3 or t.isdigit())))


def relevant(row: dict, terms: list[str]) -> bool:
    """Drop off-topic hits (e.g. Bing RSS ignoring half the query): all of 1-2 key terms, else >= 60 %."""
    if not terms:
        return True
    hay = f"{row.get('title', '')} {row.get('snippet', '')} {urllib.parse.unquote(row.get('url', ''))}".lower()
    hit = sum(1 for t in terms if t in hay)
    need = len(terms) if len(terms) <= 2 else -(-len(terms) * 3 // 5)  # all of 1-2 terms, else 60 %
    return hit >= need


def _norm(url: str) -> str:
    p = urllib.parse.urlsplit(url.strip())
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    q = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(p.query)
                                if not k.lower().startswith(("utm_", "fbclid", "gclid"))])
    return f"{host}{p.path.rstrip('/')}?{q}".lower()


def _gemini_grounded(query: str, key: str, timeout: float = 20.0) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GROUNDING_MODEL}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"Search the web and answer briefly with facts: {query}"}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.2},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}") from None
    cand = (raw.get("candidates") or [{}])[0]
    text = " ".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or []).strip()
    sources = []
    for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks") or []:
        w = ch.get("web") or {}
        r = _row(w.get("title"), w.get("uri"), "", "gemini_google_search")
        if r:
            sources.append(r)
    return {"summary": text[:1500], "results": sources[:5]}


# ---------- main ----------
def search(query: str, max_results: int = 5, gemini_key: str = "", *, ddgs_fn=None, grounded_fn=None,
           fetchers=None, sleep=time.sleep) -> dict:
    """Returns {"ok", "data": {query, engine, engines, results[{title,url,snippet,source}], attempts}}
    or {"ok": False, "error", "attempts"}. Never fabricates results."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query"}
    max_results = max(1, min(int(max_results or 5), 10))
    if fetchers is None:
        fetchers = default_chain(q)
        if ddgs_fn is not None:
            fetchers = [(n, ddgs_fn if n == "ddgs" else f) for n, f in fetchers]
    grounded_fn = grounded_fn or _gemini_grounded
    deadline = time.monotonic() + OVERALL_TIMEOUT
    results: list[dict] = []
    seen: set[str] = set()
    attempts: list[dict] = []
    terms = _terms(q)
    per_source = max(3, max_results // 2 + 1)  # leave room so several engines get cited
    for name, fn in fetchers:
        if len(results) >= max_results:
            break
        left = deadline - time.monotonic()
        if left <= 0.2:
            attempts.append({"source": name, "ok": False, "n": 0, "ms": 0, "error": "skipped (overall timeout)"})
            continue
        t0 = time.monotonic()
        err, rows = "", []
        for attempt in range(RETRIES + 1):
            try:
                rows = _with_timeout(lambda: fn(q, max_results), min(SOURCE_TIMEOUT, left)) or []
                err = ""
                break
            except (Retryable, TimeoutError) as e:
                err = str(e)[:100] or type(e).__name__
                left = deadline - time.monotonic()
                if attempt < RETRIES and left > BACKOFF + 1:
                    sleep(BACKOFF * (attempt + 1))
                    continue
            except Exception as e:  # noqa: BLE001  (no results / parse error: do not retry)
                err = (str(e)[:100] or type(e).__name__)
                break
        added = dropped = 0
        for r in rows:
            if not isinstance(r, dict) or not r.get("url"):
                continue
            if added >= per_source:
                break
            if name in LOOSE and not relevant(r, terms):
                dropped += 1
                continue
            r.setdefault("source", name)
            k = _norm(r["url"])
            tk = "t:" + re.sub(r"[^a-z0-9]+", " ", r.get("title", "").lower()).strip()
            if k in seen or (len(tk) > 12 and tk in seen):
                continue
            seen.update((k, tk))
            results.append(r)
            added += 1
        attempts.append({"source": name, "ok": bool(rows) and not err, "n": added, "off_topic": dropped,
                         "ms": int((time.monotonic() - t0) * 1000), "error": err or ("" if rows else "no results")})
    if results:
        engines = list(dict.fromkeys(r["source"] for r in results[:max_results]))
        return {"ok": True, "data": {"query": q, "engine": engines[0], "engines": engines,
                                     "results": results[:max_results], "attempts": attempts}}
    if gemini_key:
        try:
            g = grounded_fn(q, gemini_key)
            if g.get("summary") or g.get("results"):
                attempts.append({"source": "gemini_google_search", "ok": True, "n": len(g.get("results") or []),
                                 "ms": 0, "error": ""})
                return {"ok": True, "data": {"query": q, "engine": "gemini_google_search",
                                             "engines": ["gemini_google_search"], "attempts": attempts, **g}}
            attempts.append({"source": "gemini_google_search", "ok": False, "n": 0, "ms": 0, "error": "empty"})
        except Exception as e:
            attempts.append({"source": "gemini_google_search", "ok": False, "n": 0, "ms": 0, "error": str(e)[:80]})
    errs = "; ".join(f"{a['source']}: {a['error']}" for a in attempts)
    return {"ok": False, "error": "web search failed — every source failed (" + errs + ")", "attempts": attempts}
