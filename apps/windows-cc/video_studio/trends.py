"""Trend research: Google Trends daily RSS + YouTube video signals + web/news search."""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
NS = {"ht": "https://trends.google.com/trending/rss"}
# Topics a family/health channel should not turn into a cheerful 3D short.
AVOID = re.compile(
    r"\b(?:death|dead|dies|died|killed|kill|murder|rape|accident|crash|blast|attack|suicide|terror|gang|gangster|"
    r"shot|shooting|arrest|arrested|riot|stampede|fire|flood toll|bishnoi|bomb|war)\b|"
    r"मौत|हत्या|हमला|गैंग|गिरफ्तार|हादसा", re.I)


def fetch_google_trends(geo: str = "IN", timeout: float = 15.0, *, fetch=None) -> list[dict]:
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    if fetch:
        xml = fetch(url)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            xml = r.read().decode("utf-8", errors="replace")
    root = ET.fromstring(xml)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        news = []
        for n in it.findall("ht:news_item", NS):
            news.append({"title": (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip(),
                         "url": (n.findtext("ht:news_item_url", default="", namespaces=NS) or "").strip(),
                         "source": (n.findtext("ht:news_item_source", default="", namespaces=NS) or "").strip()})
        out.append({"title": title, "traffic": (it.findtext("ht:approx_traffic", default="", namespaces=NS) or ""),
                    "news": [n for n in news if n["url"]]})
    return out


def safe_trends(trends: list[dict]) -> list[dict]:
    keep = []
    for t in trends:
        text = t["title"] + " " + " ".join(n["title"] for n in t["news"])
        if not AVOID.search(text):
            keep.append(t)
    return keep


def youtube_signals(query: str, max_results: int = 6) -> list[dict]:
    from ddgs import DDGS

    rows = DDGS(timeout=8).videos(query, region="in-en", max_results=max_results)
    out = []
    for r in rows or []:
        url = str(r.get("content") or r.get("embed_url") or "")
        if "youtube.com" not in url and "youtu.be" not in url:
            continue
        stats = r.get("statistics") or {}
        out.append({"title": str(r.get("title") or "")[:140], "url": url[:200],
                    "publisher": str(r.get("uploader") or r.get("publisher") or "")[:60],
                    "views": stats.get("viewCount"), "published": str(r.get("published") or "")[:25]})
    return out


def news_search(query: str, max_results: int = 6) -> list[dict]:
    from ddgs import DDGS

    rows = DDGS(timeout=8).news(query, region="in-en", max_results=max_results)
    return [{"title": str(r.get("title") or "")[:160], "url": str(r.get("url") or "")[:300],
             "snippet": str(r.get("body") or "")[:400], "source": str(r.get("source") or "")[:60]}
            for r in rows or [] if r.get("url")]
