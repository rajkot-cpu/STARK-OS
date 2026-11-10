import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import screen  # noqa: E402
import web_search  # noqa: E402


class WebSearchTests(unittest.TestCase):
    def test_ddgs_results(self):
        rows = [{"title": "T", "url": "https://x", "snippet": "s"}]
        r = web_search.search("q", ddgs_fn=lambda q, n: rows)
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["engine"], "ddgs")

    def test_falls_back_to_gemini_grounding(self):
        def boom(q, n):
            raise TimeoutError("slow")
        r = web_search.search("q", gemini_key="k", ddgs_fn=boom,
                              grounded_fn=lambda q, k: {"summary": "S", "results": []})
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["engine"], "gemini_google_search")

    def test_timeout_is_short(self):
        import time
        with mock.patch.object(web_search, "OVERALL_TIMEOUT", 0.2):
            t = time.time()
            r = web_search.search("q", ddgs_fn=lambda q, n: time.sleep(3))
            self.assertLess(time.time() - t, 1.5)
        self.assertFalse(r["ok"])

    def test_empty_query(self):
        self.assertFalse(web_search.search("  ")["ok"])

    def test_agent_tool_is_r1(self):
        from agent_tools import AgentTools
        import tempfile
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(web_search, "_ddgs", lambda q, n: [{"title": "a", "url": "https://a", "snippet": ""}]):
            r = AgentTools(Path(d)).call("web_search", {"query": "x"})
        self.assertTrue(r["ok"])
        self.assertNotIn("needs_r3", r)


class ScreenTests(unittest.TestCase):
    def test_agent_screen_read_always_needs_r3(self):
        from agent_tools import AgentTools
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            r = AgentTools(Path(d)).call("screen_read", {"question": "what", "confirmed": True})
        self.assertTrue(r["needs_r3"])
        self.assertEqual(r["kind"], "screen")

    def test_read_screen_gemini_then_openai(self):
        def gfail(*a):
            raise RuntimeError("Gemini HTTP 500")
        r = screen.read_screen("q", gemini_key="g", openai_key="o", capture=lambda: b"jpg",
                               gemini_fn=gfail, openai_fn=lambda j, q, k: "desc")
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["provider"], "openai")

    def test_no_key(self):
        self.assertFalse(screen.read_screen("q", capture=lambda: b"x")["ok"])

    def test_capture_downscales_to_jpeg(self):
        try:
            import mss  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            self.skipTest("mss/PIL missing")

        class Shot:
            size = (2560, 1440)
            bgra = b"\x10\x20\x30\x00" * (2560 * 1440)

        class Sct:
            monitors = [{}, {"left": 0}]
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def grab(self, m): return Shot()

        with mock.patch("mss.mss", lambda: Sct()):
            jpeg = screen.capture_jpeg()
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(jpeg))
        self.assertEqual(img.format, "JPEG")
        self.assertEqual(img.width, 1280)


if __name__ == "__main__":
    unittest.main()
