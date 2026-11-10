import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_studio.request import parse_request  # noqa: E402
from video_studio.script import ScriptError, parse_script, slugify  # noqa: E402
from voice_intents import match  # noqa: E402


class VideoIntentTests(unittest.TestCase):
    def test_routes_video_commands_to_video_agent(self):
        for text in [
            "Jarvis, make a 3D YouTube video on today's trend",
            "make a video about black holes",
            "make a short on cricket world cup",
            "create a 3d short on today's trend in India",
            "`make a 3D short on today's trend in India`",
            "generate a youtube short about GST",
            "ek video banao on monsoon",
            "start the video agent: diwali sweets",
        ]:
            m = match(text)
            self.assertEqual(m["intent"], "agent", text)
            self.assertEqual(m["role"], "video", text)

    def test_not_video(self):
        self.assertEqual(match("make a video call to mom")["role"] if match("make a video call to mom")["intent"] == "agent" else "chat", "chat")
        self.assertEqual(match("build a video player app")["role"], "builder")
        self.assertEqual(match("build me a snake game in html")["role"], "builder")
        self.assertEqual(match("start trading")["intent"], "start_trading")


class RequestTests(unittest.TestCase):
    def test_trend_auto(self):
        r = parse_request("Make a 3D YouTube video on today's trend")
        self.assertIsNone(r["topic"])
        self.assertEqual(r["lang"], "en")
        self.assertEqual(r["orientation"], "portrait")
        self.assertEqual(r["geo"], "IN")

    def test_explicit_topic_hindi_landscape(self):
        r = parse_request("make a landscape video about monsoon health tips in hindi")
        self.assertEqual(r["topic"], "monsoon health tips")
        self.assertEqual(r["lang"], "hi")
        self.assertEqual(r["orientation"], "landscape")

    def test_seconds(self):
        self.assertEqual(parse_request("make a 45 second short on chess")["seconds"], 45)
        self.assertEqual(parse_request("make a 300 sec short on chess")["seconds"], 90)
        self.assertEqual(parse_request("make a short on chess")["topic"], "chess")

    def test_trend_in_india(self):
        r = parse_request("Make a 3D short on today's trend in India")
        self.assertIsNone(r["topic"])


GOOD = {
    "title": "Why Everyone Is Talking About Chess",
    "description": "A quick look.",
    "tags": ["chess", "india", "#shorts"],
    "scenes": [
        {"narration": "Chess is trending across India today. " * 2, "on_screen_text": "Chess is trending",
         "visual": {"shape": "cube", "colors": ["#ff0000", "#00ff00"], "camera": "orbit"}},
        {"narration": "Here is why the world is watching closely.", "on_screen_text": "Why?",
         "visual": {"shape": "blob", "colors": ["red"], "camera": "warp", "background": ["#000000", "#111111"]}},
        {"narration": "Follow for more trends every day.", "on_screen_text": "Follow",
         "visual": {}},
    ],
}


class ScriptTests(unittest.TestCase):
    def test_parses_fenced_json_and_normalizes(self):
        s = parse_script("```json\n" + json.dumps(GOOD) + "\n```")
        self.assertEqual(len(s["scenes"]), 3)
        v = s["scenes"][1]["visual"]
        self.assertEqual(v["shape"], "sphere")          # unknown -> default
        self.assertEqual(v["camera"], "orbit")          # unknown -> default
        self.assertTrue(all(c.startswith("#") and len(c) == 7 for c in v["colors"]))
        self.assertEqual(len(v["colors"]), 2)
        self.assertEqual(s["scenes"][0]["visual"]["colors"][0], "#ff0000")
        self.assertIn("shorts", [t.lstrip("#") for t in s["tags"]])

    def test_rejects_too_few_scenes(self):
        bad = dict(GOOD, scenes=GOOD["scenes"][:1])
        with self.assertRaises(ScriptError):
            parse_script(json.dumps(bad))

    def test_rejects_garbage(self):
        with self.assertRaises(ScriptError):
            parse_script("sorry I can't")

    def test_caps_scenes_and_text(self):
        many = dict(GOOD, title="x" * 300, scenes=[GOOD["scenes"][0]] * 15)
        s = parse_script(json.dumps(many))
        self.assertLessEqual(len(s["scenes"]), 8)
        self.assertLessEqual(len(s["title"]), 100)

    def test_drops_empty_narration(self):
        sc = GOOD["scenes"] + [{"narration": "  ", "visual": {}}]
        s = parse_script(json.dumps(dict(GOOD, scenes=sc)))
        self.assertEqual(len(s["scenes"]), 3)

    def test_slugify(self):
        self.assertEqual(slugify("Why Everyone Is Talking About Chess!"), "why-everyone-is-talking-about-chess")
        self.assertTrue(slugify("लॉरेंस बिश्नोई"))
        self.assertLessEqual(len(slugify("a" * 200)), 48)


if __name__ == "__main__":
    unittest.main()
