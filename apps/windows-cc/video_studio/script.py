"""Parse + validate the LLM's scene-list JSON into a safe, renderable script."""
from __future__ import annotations

import json
import re
import unicodedata

SHAPES = ("cube", "sphere", "torus", "pyramid", "icosahedron", "octahedron", "bars", "rings", "globe", "helix")
CAMERAS = ("orbit", "zoom_in", "zoom_out", "pan", "rise")
MOTIONS = ("spin", "pulse", "float")
PALETTES = [
    ("#00e5ff", "#ff2bd6"), ("#ffb300", "#ff3d00"), ("#76ff03", "#00b0ff"),
    ("#e040fb", "#3d5afe"), ("#ffd740", "#00e676"), ("#ff4081", "#7c4dff"),
]
BACKGROUNDS = [("#05061a", "#1a0b3d"), ("#020b14", "#0b3a4a"), ("#0d0221", "#3b0a45"),
               ("#000000", "#14213d"), ("#04120a", "#0b3d2e"), ("#1a0505", "#3d1a0b")]
_NAMED = {"red": "#ff3b30", "green": "#34c759", "blue": "#0a84ff", "yellow": "#ffd60a", "orange": "#ff9f0a",
          "purple": "#bf5af2", "pink": "#ff2d55", "cyan": "#00e5ff", "white": "#f5f5f7", "gold": "#ffc94a",
          "teal": "#30d5c8", "magenta": "#ff2bd6", "black": "#000000", "silver": "#c0c0c0"}
MIN_SCENES, MAX_SCENES = 3, 8


class ScriptError(ValueError):
    pass


def _extract_json(text: str):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(t[a:b + 1])
        except json.JSONDecodeError as e:
            raise ScriptError(f"script is not valid JSON: {e}") from None
    raise ScriptError("script reply contained no JSON object")


def _color(v, fallback: str) -> str:
    s = str(v or "").strip().lower()
    if s in _NAMED:
        return _NAMED[s]
    if re.fullmatch(r"#?[0-9a-f]{6}", s):
        return "#" + s.lstrip("#")
    if re.fullmatch(r"#?[0-9a-f]{3}", s):
        s = s.lstrip("#")
        return "#" + "".join(c * 2 for c in s)
    return fallback


def _colors(v, palette) -> list[str]:
    vals = v if isinstance(v, list) else ([v] if v else [])
    out = [_color(vals[i] if i < len(vals) else None, palette[i]) for i in range(2)]
    return out


def _clip(s, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def parse_script(text_or_obj) -> dict:
    obj = text_or_obj if isinstance(text_or_obj, dict) else _extract_json(text_or_obj)
    if not isinstance(obj, dict):
        raise ScriptError("script must be a JSON object")
    raw_scenes = obj.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ScriptError("script has no scenes list")
    scenes = []
    for i, sc in enumerate(raw_scenes):
        if not isinstance(sc, dict):
            continue
        narration = _clip(sc.get("narration"), 400)
        if not narration:
            continue
        v = sc.get("visual") if isinstance(sc.get("visual"), dict) else {}
        k = len(scenes)
        shape = str(v.get("shape") or "").lower().strip()
        camera = str(v.get("camera") or "").lower().strip().replace(" ", "_").replace("-", "_")
        motion = str(v.get("motion") or "").lower().strip()
        scenes.append({
            "narration": narration,
            "on_screen_text": _clip(sc.get("on_screen_text") or sc.get("text"), 60),
            "visual": {
                "shape": shape if shape in SHAPES else ("sphere" if shape else SHAPES[k % len(SHAPES)]),
                "colors": _colors(v.get("colors"), PALETTES[k % len(PALETTES)]),
                "background": _colors(v.get("background"), BACKGROUNDS[k % len(BACKGROUNDS)]),
                "camera": camera if camera in CAMERAS else ("orbit" if camera else CAMERAS[k % len(CAMERAS)]),
                "motion": motion if motion in MOTIONS else "spin",
            },
        })
        if len(scenes) >= MAX_SCENES:
            break
    if len(scenes) < MIN_SCENES:
        raise ScriptError(f"script needs at least {MIN_SCENES} scenes with narration (got {len(scenes)})")
    tags = obj.get("tags") if isinstance(obj.get("tags"), list) else []
    tags = [_clip(t, 40).lstrip("#") for t in tags if str(t or "").strip()][:15]
    if "shorts" not in [t.lower() for t in tags]:
        tags.append("shorts")
    title = _clip(obj.get("title") or scenes[0]["on_screen_text"] or "Trending now", 100)
    return {
        "title": title,
        "description": _clip(obj.get("description"), 1500),
        "tags": tags,
        "scenes": scenes,
    }


def word_count(script: dict) -> int:
    return sum(len(s["narration"].split()) for s in script["scenes"])


def slugify(text: str, n: int = 48) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if not t:
        t = "video"
    return t[:n].rstrip("-") or "video"
