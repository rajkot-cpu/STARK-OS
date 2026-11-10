# apps/windows-cc/web_search.py
"""Read-only web search for agents (R1): ddgs first, Gemini google_search grounding fallback."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

DDGS_TIMEOUT = 5
OVERALL_TIMEOUT = 12.0
# Measured on chandan 2026-11-10: yahoo ~1.2 s; "auto" works but is flaky/slow.
BACKENDS = ("yahoo", "auto")
GROUNDING_MODEL = "gemini-3.1-flash-lite-preview"


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
    out = []
    for r in rows or []:
        out.append({
            "title": str(r.get("title") or "")[:160],
            "url": str(r.get("href") or r.get("url") or "")[:300],
            "snippet": str(r.get("body") or "")[:300],
        })
    return [r for r in out if r["url"]]


def _with_timeout(fn, timeout: float):
    box: dict = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"search timed out after {timeout:.0f}s")
    if "e" in box:
        raise box["e"]
    return box.get("v")


def _gemini_grounded(query: str, key: str, timeout: float = 20.0) -> dict:
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GROUNDING_MODEL}:generateContent?key={key}")
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"Search the web and answer briefly with facts: {query}"}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"maxOutputTokens": 400, "temperature": 0.2},
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}") from None  # never echo URL (has key)
    cand = (raw.get("candidates") or [{}])[0]
    text = " ".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or []).strip()
    sources = []
    for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks") or []:
        w = ch.get("web") or {}
        if w.get("uri"):
            sources.append({"title": str(w.get("title") or "")[:160], "url": str(w["uri"])[:300]})
    return {"summary": text[:1500], "results": sources[:5]}


def search(query: str, max_results: int = 5, gemini_key: str = "", *, ddgs_fn=None, grounded_fn=None) -> dict:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty query"}
    max_results = max(1, min(int(max_results or 5), 8))
    ddgs_fn = ddgs_fn or _ddgs
    grounded_fn = grounded_fn or _gemini_grounded
    errors = []
    try:
        rows = _with_timeout(lambda: ddgs_fn(q, max_results), OVERALL_TIMEOUT)
        if rows:
            return {"ok": True, "data": {"query": q, "engine": "ddgs", "results": rows[:max_results]}}
        errors.append("ddgs: no results")
    except Exception as e:
        errors.append(f"ddgs: {type(e).__name__}")
    if gemini_key:
        try:
            g = grounded_fn(q, gemini_key)
            if g.get("summary") or g.get("results"):
                return {"ok": True, "data": {"query": q, "engine": "gemini_google_search", **g}}
            errors.append("gemini: empty")
        except Exception as e:
            errors.append(f"gemini: {str(e)[:80]}")
    return {"ok": False, "error": "web search failed (" + "; ".join(errors) + ")"}
