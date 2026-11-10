"""Turn a spoken/typed video goal into a job request."""
from __future__ import annotations

import re

_TREND = re.compile(r"\b(?:today'?s?|todays|current|latest|top|what'?s|whats)?\s*(?:trend|trends|trending)\b", re.I)
_HINDI = re.compile(r"\b(?:in\s+hindi|hindi\s+(?:me|mein|language)|hindi)\b|हिंदी|हिन्दी", re.I)
_LAND = re.compile(r"\b(?:landscape|horizontal|widescreen|16\s*:\s*9|1920\s*x\s*1080|long\s+video|full\s+video)\b", re.I)
_SECS = re.compile(r"\b(\d{1,3})\s*(?:s|sec|secs|second|seconds)\b", re.I)
_MIN = re.compile(r"\b(\d)\s*(?:min|mins|minute|minutes)\b", re.I)
_TOPIC = re.compile(r"\b(?:on|about|regarding|covering|explaining|for)\s+(.+)$", re.I)
_TAIL = re.compile(
    r"(?:\s+(?:in\s+hindi|in\s+english|for\s+(?:my\s+)?(?:youtube|channel|shorts?)|as\s+a\s+short|"
    r"in\s+3d|in\s+(?:landscape|portrait)|with\s+voice(?:over)?|please|now|today))+\s*$", re.I)
_GEO = {"india": "IN", "us": "US", "usa": "US", "america": "US", "uk": "GB", "britain": "GB",
        "world": "IN", "global": "IN"}


def parse_request(goal: str) -> dict:
    g = re.sub(r"\s+", " ", (goal or "").strip().strip("`\"'.!"))
    lang = "hi" if _HINDI.search(g) else "en"
    orientation = "landscape" if _LAND.search(g) else "portrait"
    seconds = 60
    m = _SECS.search(g)
    if m:
        seconds = int(m.group(1))
    else:
        m = _MIN.search(g)
        if m:
            seconds = int(m.group(1)) * 60
    seconds = max(30, min(90, seconds))
    geo = "IN"
    topic = None
    m = _TOPIC.search(g)
    if m:
        t = m.group(1).strip()
        for _ in range(3):
            t = _TAIL.sub("", t).strip(" ,.!")
        gm = re.search(r"\bin\s+(india|us|usa|america|uk|britain|world|global)\s*$", t, re.I)
        if gm and _TREND.search(t):
            geo = _GEO[gm.group(1).lower()]
        if _TREND.search(t) or not t:
            topic = None
        else:
            topic = t[:120]
    return {"topic": topic, "lang": lang, "orientation": orientation, "seconds": seconds,
            "geo": geo, "goal": g}
