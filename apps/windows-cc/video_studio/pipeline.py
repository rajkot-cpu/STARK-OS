"""Video Studio orchestration: request -> research -> script -> voiceover -> 3D render -> MP4.

Every external effect goes through `Deps`, so the whole flow is testable with fakes.
Nothing is uploaded anywhere: output stays in workspace/videos/<slug>/.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import audio as A
from .request import parse_request
from .script import ScriptError, parse_script, slugify, word_count, SHAPES, CAMERAS, MOTIONS
from .subs import build_ass
from .trends import safe_trends

FPS = 30
MAX_SECONDS = 95.0
VOICES = {"en": "en-IN-PrabhatNeural", "hi": "hi-IN-MadhurNeural"}
SIZES = {"portrait": (1080, 1920), "landscape": (1920, 1080)}


class Cancelled(RuntimeError):
    pass


@dataclass
class Deps:
    llm: Callable[..., tuple[str, str]]          # (system, prompt, json_mode=bool) -> (text, provider)
    trends: Callable[[str], list]                # geo -> google trends items
    news: Callable[[str], list]                  # query -> [{title,url,snippet,source}]
    youtube: Callable[[str], list]               # query -> [{title,url,publisher,views}]
    tts: Callable[[str, str, str], str]          # (text, voice, out_base_no_ext) -> written audio path
    ffmpeg: object                               # to_wav / open_encoder / thumbnail / probe
    frames: Callable[..., object]                # render_scene_frames-compatible
    fonts_dir: Callable[[Path], str | None] = lambda root: None
    font: str = "Nirmala UI"
    sizes: dict = field(default_factory=lambda: dict(SIZES))
    fps: int = FPS


PICK_SYSTEM = (
    "You pick ONE topic for a short, upbeat, family-friendly explainer video for an Indian YouTube audience. "
    "Avoid crime, violence, deaths, tragedies, communal or election controversy, and anything defamatory. "
    "Prefer topics with clear, verifiable facts (sports results, science, technology, festivals, weather, "
    "health awareness, economy, entertainment releases). Reply with JSON only: "
    '{"index": <number from the list>, "topic": "<short English topic name>", "angle": "<one-line angle>"}'
)


def _script_system(lang: str) -> str:
    language = ("Hindi in Devanagari script (simple conversational Hindi, common English words are fine)"
                if lang == "hi" else "simple Indian English")
    return (
        "You write scripts for animated 3D YouTube videos. Write narration and on-screen text in "
        f"{language}. Use ONLY facts found in the research notes; if a number or claim is not in the notes, "
        "do not state it. No medical or financial advice beyond general awareness. Start with a strong hook, "
        "end with a call to follow the channel. Reply with JSON only, matching exactly:\n"
        '{"title": str (<=70 chars, no emoji), "description": str (2-3 sentences), "tags": [8-12 strings], '
        '"scenes": [{"narration": str, "on_screen_text": str (<=6 words), "visual": {'
        f'"shape": one of {list(SHAPES)}, "colors": ["#rrggbb", "#rrggbb"], '
        '"background": ["#rrggbb dark", "#rrggbb dark"], '
        f'"camera": one of {list(CAMERAS)}, "motion": one of {list(MOTIONS)}' + "}}]}\n"
        "Choose shapes that suit each scene (bars for numbers/growth, globe for world/geography, helix for "
        "health/science, rings for space/energy, torus/sphere/cube etc for general). Use vivid neon colors on "
        "dark backgrounds."
    )


def _emit(progress, msg, replace=False):
    if progress:
        try:
            progress(msg, replace)
        except TypeError:
            progress(msg)


def _check(should_stop):
    if should_stop and should_stop():
        raise Cancelled("stopped by operator")


def _unique_dir(base: Path, slug: str) -> Path:
    d = base / slug
    k = 2
    while d.exists():
        d = base / f"{slug}-{k}"
        k += 1
    d.mkdir(parents=True)
    return d


def research(req: dict, deps: Deps, progress=None) -> dict:
    trends_used, why, angle = [], "", ""
    topic = req["topic"]
    pick_provider = ""
    if not topic:
        _emit(progress, f"1/6 Researching trends (Google Trends {req['geo']} + YouTube)")
        try:
            trends_used = deps.trends(req["geo"])
        except Exception as e:  # noqa: BLE001
            _emit(progress, f"⚠ Google Trends unavailable ({type(e).__name__}); using news search")
        safe = safe_trends(trends_used)[:12]
        if safe:
            listing = "\n".join(
                f"{i + 1}. {t['title']} (searches: {t['traffic'] or '?'}) — "
                + " | ".join(n["title"] for n in t["news"][:2]) for i, t in enumerate(safe))
            try:
                text, pick_provider = deps.llm(PICK_SYSTEM, f"Today's Google Trends ({req['geo']}):\n{listing}",
                                               json_mode=True)
                obj = json.loads(text[text.find("{"): text.rfind("}") + 1])
                i = int(obj.get("index") or 1) - 1
                chosen = safe[i if 0 <= i < len(safe) else 0]
                topic = str(obj.get("topic") or chosen["title"]).strip()[:120]
                angle = str(obj.get("angle") or "").strip()[:200]
            except Exception:  # noqa: BLE001
                chosen = safe[0]
                topic = chosen["title"]
            why = f"Google Trends {req['geo']}: '{chosen['title']}' ({chosen['traffic'] or 'trending'} searches today)"
            trend_news = chosen["news"][:3]
        else:
            topic, trend_news = "what India is searching for today", []
            why = "No safe Google Trends item; general trending topic"
    else:
        _emit(progress, f"1/6 Researching: {topic}")
        trend_news = []
        why = "Topic given by operator"
    sources = [{"title": n["title"], "url": n["url"], "source": n.get("source", "")} for n in trend_news]
    notes = [n["title"] for n in trend_news]
    try:
        for r in deps.news(f"{topic}")[:6]:
            if r["url"] not in {s["url"] for s in sources}:
                sources.append({"title": r["title"], "url": r["url"], "source": r.get("source", "")})
                notes.append(f"{r['title']}: {r.get('snippet', '')}")
    except Exception as e:  # noqa: BLE001
        _emit(progress, f"⚠ news search failed ({type(e).__name__})")
    yt = []
    try:
        yt = deps.youtube(f"{topic}")[:6]
    except Exception:  # noqa: BLE001
        pass
    return {"topic": topic, "angle": angle, "why": why, "sources": sources[:8], "notes": notes[:10],
            "youtube": yt, "trends": [t["title"] for t in trends_used][:15], "pick_provider": pick_provider}


def write_script(req: dict, res: dict, deps: Deps, progress=None) -> tuple[dict, str]:
    _emit(progress, f"2/6 Writing the script on '{res['topic']}'")
    target = int(req["seconds"] * (2.3 if req["lang"] == "en" else 2.1))
    notes = "\n".join(f"[{i + 1}] {n}" for i, n in enumerate(res["notes"])) or "(no notes found — keep it general)"
    yt = "\n".join(f"- {v['title']}" for v in res["youtube"][:5]) or "(none)"
    prompt = (
        f"Topic: {res['topic']}\nAngle: {res['angle'] or 'explain why it is trending and what it means'}\n"
        f"Format: {'vertical YouTube Short' if req['orientation'] == 'portrait' else 'landscape YouTube video'}, "
        f"about {req['seconds']} seconds.\nWrite 5-7 scenes, about {target} words of narration in total "
        f"(each scene 15-30 words).\nResearch notes:\n{notes}\nExisting YouTube videos on this topic "
        f"(for what works, do not copy):\n{yt}\nOperator request: {req['goal']}"
    )
    system = _script_system(req["lang"])
    last_err, provider = "", ""
    for attempt in range(2):
        p = prompt if not last_err else prompt + f"\n\nYour previous reply was invalid ({last_err}). Reply with the JSON object only."
        text, provider = deps.llm(system, p, json_mode=True)
        try:
            return parse_script(text), provider
        except ScriptError as e:
            last_err = str(e)
            _emit(progress, f"⚠ script invalid ({last_err[:60]}), asking again")
    raise ScriptError(last_err)


def voiceover(script: dict, req: dict, out: Path, deps: Deps, progress=None, should_stop=None):
    voice = VOICES.get(req["lang"], VOICES["en"])
    _emit(progress, f"3/6 Recording voiceover ({voice.split('-')[2].replace('Neural', '')}, {len(script['scenes'])} scenes)")
    adir = out / "audio"
    adir.mkdir(exist_ok=True)
    clips = []
    for i, sc in enumerate(script["scenes"]):
        _check(should_stop)
        src = deps.tts(sc["narration"], voice, str(adir / f"scene{i + 1}"))
        wav = str(adir / f"scene{i + 1}.wav")
        if not src.lower().endswith(".wav") or src != wav:
            deps.ffmpeg.to_wav(src, wav)
        clips.append(A.read_wav(wav))
    # Keep v1 within ~90 s: drop trailing scenes (never below 3).
    while len(clips) > 3 and A.timeline(clips)[1] > MAX_SECONDS:
        clips.pop()
        script["scenes"].pop()
    track, scenes, total = A.mix(clips)
    A.write_wav(str(out / "audio.wav"), track)
    return scenes, total, voice


def render(script: dict, scenes, total: float, req: dict, out: Path, root: Path, deps: Deps,
           progress=None, should_stop=None) -> None:
    W, H = deps.sizes[req["orientation"]]
    fps = deps.fps
    (out / "subs.ass").write_text(build_ass(script, scenes, W, H, font=deps.font), encoding="utf-8")
    fonts = deps.fonts_dir(root)
    rel_fonts = os.path.relpath(fonts, out).replace("\\", "/") if fonts else None
    _emit(progress, f"4/6 Rendering 3D scenes ({W}x{H}, {total:.0f}s, {int(total * fps)} frames)")
    proc = deps.ffmpeg.open_encoder(str(out), W, H, fps, "audio.wav", "subs.ass", rel_fonts)
    nframes = int(round(total * fps))
    done, last_pct, t_start = 0, -1, time.time()
    try:
        for k, (sc, (s, d)) in enumerate(zip(script["scenes"], scenes)):
            n_this = int(round((s + d) * fps)) - int(round(s * fps))
            for buf in deps.frames(sc["visual"], W, H, n_this / fps, fps, seed=k, t0=s):
                _check(should_stop)
                proc.stdin.write(buf)
                done += 1
                pct = done * 100 // max(1, nframes)
                if pct // 5 != last_pct // 5:
                    last_pct = pct
                    el = time.time() - t_start
                    eta = el / max(done, 1) * (nframes - done)
                    _emit(progress, f"rendering {pct}% (scene {k + 1}/{len(scenes)}, ~{int(eta)}s left)", True)
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        if proc.stderr:
            proc.stderr.close()
        rc = proc.wait(timeout=600)
        if rc != 0:
            raise RuntimeError(f"ffmpeg encode failed ({rc}): {err.strip()[-400:]}")
    except BaseException:
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
        raise


def run_job(root: Path, goal: str, deps: Deps, progress=None, should_stop=None, now=time.localtime) -> dict:
    root = Path(root)
    req = parse_request(goal)
    t = {"start": time.time()}
    res = research(req, deps, progress)
    t["research"] = time.time()
    _check(should_stop)
    script, provider = write_script(req, res, deps, progress)
    t["script"] = time.time()
    _check(should_stop)
    base = root / "workspace" / "videos"
    base.mkdir(parents=True, exist_ok=True)
    out = _unique_dir(base, slugify(script["title"] if script["title"].isascii() else res["topic"]))
    (out / "research.json").write_text(json.dumps({"request": req, **res}, ensure_ascii=False, indent=2), encoding="utf-8")
    scenes, total, voice = voiceover(script, req, out, deps, progress, should_stop)
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    t["voice"] = time.time()
    render(script, scenes, total, req, out, root, deps, progress, should_stop)
    t["render"] = time.time()
    _emit(progress, "5/6 Thumbnail + checking the MP4")
    video = out / "video.mp4"
    deps.ffmpeg.thumbnail(str(video), min(total - 0.1, scenes[0][0] + 1.2), str(out / "thumbnail.png"))
    probe = deps.ffmpeg.probe(str(video))
    kinds = {s.get("codec_type") for s in probe["streams"]}
    if not {"video", "audio"} <= kinds or probe["duration"] <= 1:
        raise RuntimeError(f"rendered MP4 failed checks: {probe}")
    src_lines = "\n".join(f"- {s['title']} ({s.get('source') or ''}) {s['url']}" for s in res["sources"])
    meta = (
        f"TITLE:\n{script['title']}\n\nDESCRIPTION:\n{script['description']}\n\nSources:\n{src_lines or '- (none)'}\n\n"
        f"TAGS:\n{', '.join(script['tags'])}\n\n---\nTopic: {res['topic']}\nWhy: {res['why']}\n"
        f"Language: {req['lang']}  Voice: {voice}  Format: {req['orientation']}  Duration: {probe['duration']:.1f}s\n"
        f"Script AI: {provider}\nNot uploaded. Review before posting; upload is manual.\n"
    )
    (out / "metadata.txt").write_text(meta, encoding="utf-8")
    shutil.rmtree(out / "audio", ignore_errors=True)
    t["end"] = time.time()
    rel = out.relative_to(root / "workspace").as_posix()
    _emit(progress, "6/6 Done")
    return {
        "ok": True, "folder": str(out), "rel": rel, "video": str(video), "thumbnail": str(out / "thumbnail.png"),
        "metadata": str(out / "metadata.txt"), "title": script["title"], "topic": res["topic"], "why": res["why"],
        "sources": res["sources"], "duration": probe["duration"], "probe": probe, "provider": provider,
        "scenes": len(script["scenes"]), "words": word_count(script), "lang": req["lang"],
        "timings": {"research": round(t["research"] - t["start"], 1), "script": round(t["script"] - t["research"], 1),
                    "voice": round(t["voice"] - t["script"], 1), "render": round(t["render"] - t["voice"], 1),
                    "total": round(t["end"] - t["start"], 1)},
        "files": [f"{rel}/video.mp4", f"{rel}/thumbnail.png", f"{rel}/metadata.txt", f"{rel}/script.json"],
    }


# ---------------------------------------------------------------- real deps --

def _fonts_dir(root: Path) -> str | None:
    if sys.platform != "win32":
        return None
    dst = Path(root) / "tools" / "fonts"
    try:
        dst.mkdir(parents=True, exist_ok=True)
        windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in ("Nirmala.ttf", "NirmalaB.ttf", "Nirmala.ttc"):
            if (windir / name).is_file() and not (dst / name).is_file():
                shutil.copy2(windir / name, dst / name)
        return str(dst) if any(dst.iterdir()) else None
    except Exception:  # noqa: BLE001
        return None


def _tts(text: str, voice: str, base: str) -> str:
    import tts

    mp3 = base + ".mp3"
    last = None
    for attempt in range(3):
        try:
            tts.edge_synthesize(text, voice, mp3, timeout=60)
            return mp3
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    if voice.startswith("en"):
        # Offline fallback: Windows SAPI voice to wav.
        import pyttsx3

        wav = base + "-sapi.wav"
        eng = pyttsx3.init()
        eng.save_to_file(text, wav)
        eng.runAndWait()
        if os.path.isfile(wav) and os.path.getsize(wav) > 1000:
            return wav
    raise RuntimeError(f"voiceover failed (edge-tts: {type(last).__name__})")


def default_deps(root: Path, providers: list[tuple[str, str]], progress=None, on_provider=None) -> Deps:
    from . import ffmpeg_tools, render3d, trends
    from .llm import complete

    ff, fp = ffmpeg_tools.ensure(root, progress=lambda m: _emit(progress, m, True))

    def llm(system, prompt, json_mode=False):
        text, prov = complete(providers, system, prompt, json_mode=json_mode,
                              on_note=lambda m: _emit(progress, m))
        if on_provider:
            on_provider(prov)
        return text, prov

    return Deps(llm=llm, trends=trends.fetch_google_trends, news=trends.news_search,
                youtube=trends.youtube_signals, tts=_tts, ffmpeg=ffmpeg_tools.FFmpeg(ff, fp),
                frames=render3d.render_scene_frames, fonts_dir=_fonts_dir)
