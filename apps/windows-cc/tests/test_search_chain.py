import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))

import web_search  # noqa: E402

NO_SLEEP = dict(sleep=lambda s: None)


def rows(src, *urls, title="NIFTY 50 outlook"):
    return [{"title": f"{title} {i}", "url": u, "snippet": "nifty 50 outlook week", "source": src} for i, u in enumerate(urls)]


class ChainTests(unittest.TestCase):
    def test_falls_through_to_second_source_and_tags_engine(self):
        def dead(q, n):
            raise RuntimeError("No results found.")
        r = web_search.search("NIFTY 50 outlook", 4, fetchers=[("ddgs", dead), ("bing", lambda q, n: rows("bing", "https://a.in/x"))], **NO_SLEEP)
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["engines"], ["bing"])
        self.assertEqual(r["data"]["results"][0]["url"], "https://a.in/x")
        self.assertEqual([a["source"] for a in r["data"]["attempts"]], ["ddgs", "bing"])

    def test_retry_with_backoff_on_retryable(self):
        calls, sleeps = [], []

        def flaky(q, n):
            calls.append(1)
            if len(calls) == 1:
                raise web_search.Retryable("HTTP 503")
            return rows("bing", "https://b.in")
        r = web_search.search("NIFTY 50 outlook", 3, fetchers=[("bing", flaky)], sleep=sleeps.append)
        self.assertTrue(r["ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [web_search.BACKOFF])

    def test_no_retry_on_no_results(self):
        calls = []

        def empty(q, n):
            calls.append(1)
            raise RuntimeError("No results found.")
        web_search.search("x y", 3, fetchers=[("ddgs", empty)], **NO_SLEEP)
        self.assertEqual(len(calls), 1)

    def test_dedupe_by_url_and_title_and_merge_sources(self):
        a = rows("bing", "https://www.site.in/p/?utm_source=x", "https://c.in/1")
        b = [{"title": "Other NIFTY 50 outlook", "url": "https://site.in/p", "snippet": "nifty 50 outlook", "source": "google_news"},
             {"title": "NIFTY 50 outlook 1", "url": "https://dup-title.in", "snippet": "", "source": "google_news"},
             {"title": "fresh nifty 50 outlook", "url": "https://d.in", "snippet": "", "source": "google_news"}]
        r = web_search.search("NIFTY 50 outlook", 8, fetchers=[("bing", lambda q, n: a), ("google_news", lambda q, n: b)], **NO_SLEEP)
        urls = [x["url"] for x in r["data"]["results"]]
        self.assertEqual(urls, ["https://www.site.in/p/?utm_source=x", "https://c.in/1", "https://d.in"])
        self.assertEqual(r["data"]["engines"], ["bing", "google_news"])

    def test_off_topic_dropped_for_loose_engines(self):
        bad = [{"title": "Nifty | Resell effortlessly", "url": "https://nifty.ai/", "snippet": "", "source": "bing"}]
        r = web_search.search("NIFTY 50 outlook this week", 5, fetchers=[("bing", lambda q, n: bad)], **NO_SLEEP)
        self.assertFalse(r["ok"])
        self.assertEqual(r["attempts"][0]["off_topic"], 1)

    def test_all_fail_says_so_never_fakes(self):
        def boom(q, n):
            raise RuntimeError("HTTP 403")
        r = web_search.search("NIFTY", 5, fetchers=[("ddgs", boom), ("bing", boom), ("wikipedia", boom)], **NO_SLEEP)
        self.assertFalse(r["ok"])
        self.assertIn("every source failed", r["error"])
        self.assertIn("wikipedia: HTTP 403", r["error"])
        self.assertNotIn("data", r)

    def test_non_http_urls_rejected(self):
        self.assertIsNone(web_search._row("t", "javascript:alert(1)", "", "x"))
        self.assertIsNone(web_search._row("t", "file:///c:/x", "", "x"))

    def test_default_chain_order_and_keyed_first(self):
        names = [n for n, _ in web_search.default_chain("NIFTY 50 outlook this week", keys={"brave": "k", "tavily": ""})]
        self.assertEqual(names, ["brave", "ddgs", "google_news", "bing", "duckduckgo_html", "wikipedia"])
        names = [n for n, _ in web_search.default_chain("photosynthesis", keys={})]
        self.assertEqual(names, ["ddgs", "bing", "duckduckgo_html", "wikipedia", "google_news"])

    def test_parsers(self):
        rss = b"""<rss><channel><item><title>Nifty 50 week</title><link>https://x.in/a</link>
        <description>&lt;b&gt;Nifty&lt;/b&gt; up</description></item></channel></rss>"""
        self.assertEqual(web_search._rss(rss, "bing", 5)[0], {"title": "Nifty 50 week", "url": "https://x.in/a",
                                                            "snippet": "Nifty up", "source": "bing"})
        html_page = ('<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fe.in%2Fp&amp;rut=1">'
                     'E <b>page</b></a><a class="result__snippet" href="x">snip</a>')
        with mock.patch.object(web_search, "_http", lambda *a, **k: html_page.encode()):
            r = web_search._ddg_html("q", 3)
        self.assertEqual(r[0]["url"], "https://e.in/p")
        self.assertEqual(r[0]["title"], "E page")
        with mock.patch.object(web_search, "_http", lambda *a, **k: b'{"query":{"search":[{"title":"Nifty 50","snippet":"<span>x</span>"}]}}'):
            w = web_search._wikipedia("q", 3)
        self.assertEqual(w[0]["url"], "https://en.wikipedia.org/wiki/Nifty_50")


class RouterCooldownTests(unittest.TestCase):
    def test_gemini_429_falls_through_and_cools_down(self):
        import llm_router

        llm_router._cooldown.clear()
        calls = []

        def gem(*a, **k):
            calls.append("gemini")
            raise RuntimeError("HTTP 429")

        def compat(system, prompt, key, mt, to, provider):
            calls.append(provider)
            return "ok from " + provider
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(llm_router, "_cloud_chain", lambda root: [("gemini", "g"), ("groq", "q")]), \
             mock.patch.object(llm_router, "_gemini", gem), mock.patch.object(llm_router, "_openai_compat", compat), \
             mock.patch.object(llm_router, "_halted", lambda: False):
            r1 = llm_router.complete("p", "s", d)
            r2 = llm_router.complete("p", "s", d)
        self.assertEqual(r1["provider"], "groq")
        self.assertIn("gemini: HTTP 429", r1["errors"][0])
        self.assertEqual(r2["provider"], "groq")
        self.assertIn("rate-limited", r2["errors"][0])
        self.assertEqual(calls, ["gemini", "groq", "groq"])
        llm_router._cooldown.clear()


class OrchestratorCitationTests(unittest.TestCase):
    def test_report_lists_sources_with_engine_and_counts_citations(self):
        from orchestrator import Orchestrator
        from task_queue import TaskQueue
        from memory_db import MemoryDB

        with tempfile.TemporaryDirectory() as d:
            q, m = TaskQueue(Path(d)), MemoryDB(Path(d))
            src = {"ok": True, "data": {"engines": ["bing", "google_news"], "attempts": [{"source": "ddgs"}, {"source": "bing"}],
                                        "results": rows("bing", "https://a.in") + rows("google_news", "https://b.in")}}
            o = Orchestrator(Path(d), q, m, complete=lambda p, s: {"ok": True, "text": "# R\n- fact [1]\n- more [2]", "provider": "groq"},
                             search=lambda t: src)
            t = o.submit("NIFTY 50 outlook")["data"]
            done = o.wait(t["id"], 10)
            body = (Path(d) / done["result"]).read_text(encoding="utf-8")
        self.assertIn("1. [NIFTY 50 outlook 0](https://a.in) — via bing", body)
        self.assertIn("— via google_news", body)
        self.assertEqual(done["steps"][0]["engines"], ["bing", "google_news"])
        self.assertEqual(done["steps"][-1]["cited"], 2)

    def test_report_states_search_failure(self):
        from orchestrator import Orchestrator
        from task_queue import TaskQueue
        from memory_db import MemoryDB

        with tempfile.TemporaryDirectory() as d:
            q, m = TaskQueue(Path(d)), MemoryDB(Path(d))
            o = Orchestrator(Path(d), q, m, complete=lambda p, s: {"ok": True, "text": "# R\nnothing", "provider": "groq"},
                             search=lambda t: {"ok": False, "error": "web search failed — every source failed (bing: HTTP 403)"})
            done = o.wait(o.submit("x")["data"]["id"], 10)
            body = (Path(d) / done["result"]).read_text(encoding="utf-8")
        self.assertIn("every source failed (bing: HTTP 403)", body)


class ProviderTestSearchKeys(unittest.TestCase):
    def test_search_key_tests(self):
        import provider_tests

        with mock.patch.dict(os.environ, {"JARVIS_BRAVE_SEARCH_API_KEY": "brvKEY"}), mock.patch("llm_providers.load_secrets"), \
             mock.patch.dict(web_search._KEYED_FN, {"brave": lambda q, n, k: [{"url": "https://x"}]}):
            r = provider_tests.run("brave")
        self.assertTrue(r["ok"])
        self.assertNotIn("brvKEY", str(r))
        with mock.patch.dict(os.environ, {"JARVIS_SERPER_API_KEY": ""}), mock.patch("llm_providers.load_secrets"):
            self.assertEqual(provider_tests.run("serper")["status"], "missing_key")
        seen = []
        with mock.patch.dict(os.environ, {"JARVIS_SERPAPI_API_KEY": "spKEY"}), mock.patch("llm_providers.load_secrets"):
            r = provider_tests.run("serpapi", get=lambda u, h, timeout=8: (seen.append(u), (200, {"plan_id": "free"}, 5))[1])
        self.assertTrue(r["ok"])
        self.assertTrue(seen[0].startswith("https://serpapi.com/account.json"))

    def test_slots_present(self):
        import keys_manager

        names = {s["name"] for s in keys_manager.SLOTS}
        for n in ("JARVIS_TAVILY_API_KEY", "JARVIS_BRAVE_SEARCH_API_KEY", "JARVIS_SERPER_API_KEY", "JARVIS_SERPAPI_API_KEY"):
            self.assertIn(n, names)


class TaskReportTests(unittest.TestCase):
    def test_task_report_only_reads_reports_dir(self):
        import bridge_phase3

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "workspace" / "reports").mkdir(parents=True)
            (root / "workspace" / "reports" / "r.md").write_text("# hi", encoding="utf-8")
            (root / "secret.md").write_text("no", encoding="utf-8")

            class Q:
                def get(self, tid):
                    return {"result": {"good": "workspace/reports/r.md", "bad": "workspace/reports/../../secret.md"}.get(tid, "")}

            class B(bridge_phase3.Phase3Mixin):
                pass
            b = B()
            b.root = root
            b._p3 = lambda: {"queue": Q()}
            self.assertEqual(b.task_report("good")["data"]["text"], "# hi")
            self.assertFalse(b.task_report("bad")["ok"])
            self.assertFalse(b.task_report("none")["ok"])


if __name__ == "__main__":
    unittest.main()
