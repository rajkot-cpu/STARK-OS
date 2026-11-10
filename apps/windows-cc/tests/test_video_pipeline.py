import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from video_studio import audio as A  # noqa: E402
from video_studio.pipeline import Cancelled, Deps, run_job  # noqa: E402
from video_studio.render3d import render_scene_frames  # noqa: E402
from video_studio.subs import build_ass  # noqa: E402
from video_studio.trends import fetch_google_trends, safe_trends  # noqa: E402

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>gangster held</title><ht:approx_traffic>500+</ht:approx_traffic>
 <ht:news_item><ht:news_item_title>Gangster arrested</ht:news_item_title><ht:news_item_url>https://x/1</ht:news_item_url><ht:news_item_source>X</ht:news_item_source></ht:news_item></item>
<item><title>India vs NZ</title><ht:approx_traffic>20000+</ht:approx_traffic>
 <ht:news_item><ht:news_item_title>Rohit scores century</ht:news_item_title><ht:news_item_url>https://news/rohit</ht:news_item_url><ht:news_item_source>Sports</ht:news_item_source></ht:news_item></item>
</channel></rss>"""

SCRIPT = {"title": "India vs NZ: What Happened", "description": "Quick recap.", "tags": ["cricket"],
          "scenes": [{"narration": f"Scene {i} narration about the match today.", "on_screen_text": f"Part {i}",
                      "visual": {"shape": "bars", "camera": "orbit"}} for i in range(4)]}


class FakeProc:
    def __init__(self):
        self.stdin = io.BytesIO()
        self.stdin.close = lambda: None
        self.stderr = io.BytesIO(b"")
        self.frames = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class FakeFF:
    def __init__(self):
        self.proc = None
        self.enc_args = None

    def to_wav(self, src, dst):
        A.write_wav(dst, np.zeros(int(A.RATE * 2.0), dtype=np.float32) + 0.1)

    def open_encoder(self, out_dir, w, h, fps, audio, subs, fontsdir):
        self.enc_args = (out_dir, w, h, fps, audio, subs, fontsdir)
        self.proc = FakeProc()
        Path(out_dir, "video.mp4").write_bytes(b"mp4")
        return self.proc

    def thumbnail(self, video, at, dst):
        Path(dst).write_bytes(b"png")

    def probe(self, path):
        return {"duration": 9.5, "size": 3, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}


def fake_frames(visual, w, h, seconds, fps, seed=0, t0=0.0):
    for _ in range(int(round(seconds * fps))):
        yield b"\x00" * (w * h * 3)


def make_deps(llm_replies, **kw):
    calls = []

    def llm(system, prompt, json_mode=False):
        calls.append((system, prompt))
        return llm_replies.pop(0), "groq"

    def tts(text, voice, base):
        Path(base + ".mp3").write_bytes(b"mp3")
        calls.append(("tts", voice))
        return base + ".mp3"

    d = Deps(llm=llm, trends=lambda geo: fetch_google_trends(geo, fetch=lambda u: RSS),
             news=lambda q: [{"title": "Match report", "url": "https://news/report", "snippet": "NZ won", "source": "S"}],
             youtube=lambda q: [{"title": "Highlights", "url": "https://youtube.com/watch?v=1"}],
             tts=tts, ffmpeg=FakeFF(), frames=fake_frames, sizes={"portrait": (8, 16), "landscape": (16, 8)},
             fps=10, **kw)
    return d, calls


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_trend_job_end_to_end_with_fakes(self):
        deps, calls = make_deps([json.dumps({"index": 1, "topic": "India vs New Zealand ODI", "angle": "recap"}),
                                 json.dumps(SCRIPT)])
        steps = []
        r = run_job(self.root, "make a 3D short on today's trend in India", deps, progress=lambda m, rep=False: steps.append(m))
        self.assertTrue(r["ok"])
        self.assertEqual(r["topic"], "India vs New Zealand ODI")
        # the gangster item is filtered before the LLM sees it
        self.assertNotIn("gangster", calls[0][1].lower())
        self.assertIn("India vs NZ", calls[0][1])
        urls = [s["url"] for s in r["sources"]]
        self.assertIn("https://news/rohit", urls)
        self.assertIn("https://news/report", urls)
        out = Path(r["folder"])
        self.assertTrue(out.is_relative_to(self.root / "workspace" / "videos"))
        for f in ("video.mp4", "thumbnail.png", "metadata.txt", "script.json", "research.json", "subs.ass", "audio.wav"):
            self.assertTrue((out / f).is_file(), f)
        meta = (out / "metadata.txt").read_text(encoding="utf-8")
        self.assertIn("https://news/rohit", meta)
        self.assertIn("Not uploaded", meta)
        # frames written == timeline length * fps
        _o, w, h, fps, *_ = deps.ffmpeg.enc_args
        self.assertEqual((w, h), (8, 16))
        written = len(deps.ffmpeg.proc.stdin.getvalue()) // (w * h * 3)
        self.assertAlmostEqual(written / fps, A.timeline([np.zeros(int(A.RATE * 2.0))] * 4)[1], delta=0.3)
        self.assertIn(("tts", "en-IN-PrabhatNeural"), calls)
        self.assertTrue(any(s.startswith("4/6") for s in steps))

    def test_explicit_topic_hindi_skips_trends_and_uses_hindi_voice(self):
        deps, calls = make_deps([json.dumps(SCRIPT)])
        deps.trends = lambda geo: self.fail("trends should not be fetched")
        r = run_job(self.root, "make a short on monsoon health tips in hindi", deps)
        self.assertEqual(r["topic"], "monsoon health tips")
        self.assertIn(("tts", "hi-IN-MadhurNeural"), calls)
        self.assertIn("Hindi", calls[0][0])

    def test_invalid_script_is_retried_once(self):
        deps, calls = make_deps(["not json", json.dumps(SCRIPT)])
        r = run_job(self.root, "make a video about chess", deps)
        self.assertTrue(r["ok"])
        self.assertIn("previous reply was invalid", calls[1][1])

    def test_trends_failure_falls_back(self):
        deps, _ = make_deps([json.dumps(SCRIPT)])

        def boom(geo):
            raise OSError("offline")
        deps.trends = boom
        r = run_job(self.root, "make a 3d video on today's trend", deps)
        self.assertTrue(r["ok"])

    def test_stop_cancels_render(self):
        deps, _ = make_deps([json.dumps(SCRIPT)])
        n = {"k": 0}

        def stop():
            n["k"] += 1
            return n["k"] > 12
        with self.assertRaises(Cancelled):
            run_job(self.root, "make a video about chess", deps, should_stop=stop)

    def test_long_scripts_trimmed_to_90s(self):
        sc = dict(SCRIPT, scenes=SCRIPT["scenes"] * 2)
        deps, _ = make_deps([json.dumps(sc)])
        deps.ffmpeg.to_wav = lambda s, d: A.write_wav(d, np.zeros(int(A.RATE * 20), dtype=np.float32))
        r = run_job(self.root, "make a video about chess", deps)
        self.assertLessEqual(r["scenes"], 4)


class UnitBits(unittest.TestCase):
    def test_safe_trends_filters(self):
        items = fetch_google_trends("IN", fetch=lambda u: RSS)
        self.assertEqual([t["title"] for t in safe_trends(items)], ["India vs NZ"])

    def test_ass_has_title_and_captions(self):
        ass = build_ass(SCRIPT, [(0, 3), (3, 3), (6, 3), (9, 3)], 1080, 1920)
        self.assertIn("Style: Cap,Nirmala UI", ass)
        self.assertEqual(ass.count(",Title,"), 4)
        self.assertIn("Part 2", ass)

    def test_render_frames_size(self):
        v = {"shape": "torus", "colors": ["#00e5ff", "#ff2bd6"], "background": ["#000000", "#111111"],
             "camera": "zoom_in", "motion": "pulse"}
        frames = list(render_scene_frames(v, 64, 112, 0.2, 10))
        self.assertEqual(len(frames), 2)
        self.assertEqual(len(frames[0]), 64 * 112 * 3)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg")
class RealFFmpegTest(unittest.TestCase):
    def test_tiny_real_encode(self):
        from video_studio.ffmpeg_tools import FFmpeg, locate

        found = locate(Path("/nonexistent"))
        if not found:
            self.skipTest("ffmpeg lacks libass")
        with tempfile.TemporaryDirectory() as td:
            deps, _ = make_deps([json.dumps(SCRIPT)])
            deps.ffmpeg = FFmpeg(*found)
            real_to_wav = deps.ffmpeg.to_wav

            def tts(text, voice, base):
                A.write_wav(base + "-src.wav", np.sin(np.arange(int(A.RATE * 1.2)) / 9).astype(np.float32) * 0.3)
                return base + "-src.wav"
            deps.tts = tts
            deps.ffmpeg.to_wav = real_to_wav
            deps.frames = render_scene_frames
            deps.sizes = {"portrait": (180, 320), "landscape": (320, 180)}
            deps.font = "DejaVu Sans"
            r = run_job(Path(td), "make a video about chess", deps)
            self.assertGreater(r["duration"], 5)
            self.assertEqual({s["codec_type"] for s in r["probe"]["streams"]}, {"video", "audio"})
            self.assertTrue(Path(r["thumbnail"]).stat().st_size > 100)


if __name__ == "__main__":
    unittest.main()
