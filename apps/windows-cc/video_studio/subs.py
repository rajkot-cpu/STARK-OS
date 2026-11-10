"""ASS subtitles: big on-screen title per scene + word-chunk captions (libass shapes Hindi correctly)."""
from __future__ import annotations


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(s: str) -> str:
    return str(s).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunks(text: str, n: int = 5) -> list[str]:
    w = text.split()
    return [" ".join(w[i:i + n]) for i in range(0, len(w), n)] or [text]


def build_ass(script: dict, scenes: list[tuple[float, float]], width: int, height: int,
              font: str = "Nirmala UI", lead: float = 0.35) -> str:
    portrait = height > width
    cap = int(height * (0.036 if portrait else 0.055))
    ttl = int(height * (0.05 if portrait else 0.075))
    mv_cap = int(height * (0.2 if portrait else 0.08))
    mv_ttl = int(height * (0.11 if portrait else 0.07))
    margin = int(width * 0.07)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{font},{cap},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(3, cap // 12)},2,2,{margin},{margin},{mv_cap},1",
        f"Style: Title,{font},{ttl},&H0000E1FF,&H00FFFFFF,&H00200010,&H96000000,-1,0,0,0,100,100,1,0,1,"
        f"{max(4, ttl // 10)},3,8,{margin},{margin},{mv_ttl},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for i, (sc, (s, d)) in enumerate(zip(script["scenes"], scenes)):
        title = sc.get("on_screen_text") or (script["title"] if i == 0 else "")
        if title:
            lines.append(f"Dialogue: 1,{_ts(s + 0.15)},{_ts(s + d - 0.15)},Title,,0,0,0,,"
                         "{\\fad(250,200)}" + _esc(title))
        parts = chunks(sc["narration"])
        speak_start = s + (lead if i == 0 else 0)
        speak = max(0.5, d - (lead if i == 0 else 0) - 0.4)
        total_chars = sum(len(p) for p in parts) or 1
        t = speak_start
        for p in parts:
            dur = speak * len(p) / total_chars
            lines.append(f"Dialogue: 0,{_ts(t)},{_ts(t + dur)},Cap,,0,0,0,,{_esc(p)}")
            t += dur
    return "\n".join(lines) + "\n"
