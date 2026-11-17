import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import broker_live  # noqa: E402
import cc_settings  # noqa: E402
import indicators as I  # noqa: E402
import jarvis_api  # noqa: E402
import keys_manager  # noqa: E402
import llm_router  # noqa: E402
import local_llm  # noqa: E402
import market_data  # noqa: E402
import memory_db  # noqa: E402
import orchestrator  # noqa: E402
import paper_ledger  # noqa: E402
import task_queue  # noqa: E402
import trading_engine  # noqa: E402


def _series(n=520, seed=3):
    import random

    r = random.Random(seed)
    c = [20000.0]
    for _ in range(n - 1):
        c.append(c[-1] * (1 + r.gauss(0.0003, 0.009)))
    return [{"t": 1_700_000_000 + i * 86400, "o": x * 0.998, "h": x * 1.006, "l": x * 0.994, "c": x, "v": 0}
            for i, x in enumerate(c)]


class IndicatorTests(unittest.TestCase):
    def test_rsi_extremes_and_ema(self):
        up = [float(i) for i in range(1, 60)]
        self.assertEqual(I.rsi(up), 100.0)
        self.assertAlmostEqual(I.ema([1.0] * 30, 10)[-1], 1.0)
        self.assertEqual(I.sma([1, 2, 3, 4], 2)[-1], 3.5)

    def test_classic_pivots(self):
        p = I.pivots(100, 110, 90, 105)["classic"]
        self.assertAlmostEqual(p["P"], (110 + 90 + 105) / 3)
        self.assertAlmostEqual(p["R1"], 2 * p["P"] - 90)
        self.assertAlmostEqual(p["S1"], 2 * p["P"] - 110)

    def test_technicals_and_stats_are_complete(self):
        bars = _series()
        t = I.technicals(bars)
        self.assertEqual(len(t["oscillators"]), 7)
        self.assertEqual(len(t["moving_averages"]), 10)
        self.assertIn(t["summary"]["overall"]["rating"], ("STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"))
        c = [b["c"] for b in bars]
        st = I.stats(c)
        self.assertTrue(st["ok"])
        self.assertLessEqual(st["sharpe_ci95"][0], st["sharpe_ci95"][1])
        rg = I.regime(c)
        self.assertAlmostEqual(sum(rg["next"].values()), 1.0, places=6)
        wf = I.walk_forward(c)
        self.assertEqual(len(wf["folds"]), 5)
        mc = I.monte_carlo(c)
        self.assertLessEqual(mc["p5"], mc["p50"])
        self.assertLessEqual(mc["p50"], mc["p95"])


class MarketDataTests(unittest.TestCase):
    def test_parse_skips_holes_never_interpolates(self):
        raw = {"chart": {"result": [{"meta": {"symbol": "^NSEI", "regularMarketPrice": 25400.5, "chartPreviousClose": 25300,
                                              "regularMarketTime": 1763450000},
                                     "timestamp": [1, 2, 3],
                                     "indicators": {"quote": [{"open": [1, None, 3], "high": [1, None, 3],
                                                               "low": [1, None, 3], "close": [1, None, 3],
                                                               "volume": [0, 0, 0]}]}}]}}
        r = market_data.parse(raw, "NIFTY", "1d")
        self.assertTrue(r["ok"])
        self.assertEqual([b["t"] for b in r["bars"]], [1, 3])
        self.assertEqual(r["last"], 25400.5)

    def test_open_last_session_uses_yahoo_session_summary(self):
        raw = {"chart": {"result": [{"meta": {"regularMarketPrice": 110.0, "regularMarketChangePercent": 10.0,
                                              "regularMarketDayHigh": 112.0, "regularMarketDayLow": 99.0,
                                              "regularMarketTime": 50},
                                     "timestamp": [10, 40],
                                     "indicators": {"quote": [{"open": [90, 101], "high": [101, None], "low": [89, None],
                                                               "close": [100, None], "volume": [0, 0]}]}}]}}
        r = market_data.parse(raw, "NIFTY", "1d")
        self.assertEqual(r["bars"][-1], {"t": 40, "o": 101.0, "h": 112.0, "l": 99.0, "c": 110.0, "v": 0.0})
        self.assertAlmostEqual(r["prev_close"], 100.0)

    def test_unknown_symbol_and_failure_are_honest(self):
        self.assertFalse(market_data.fetch("XYZ")["ok"])
        r = market_data.fetch("NIFTY", "5m", fetch_fn=lambda url: (_ for _ in ()).throw(OSError("down")))
        self.assertFalse(r["ok"])
        self.assertIn("unavailable", r["error"])

    def test_snapshot_uses_real_bars(self):
        bars = _series()
        fake = lambda s, tf: {"ok": True, "bars": bars, "last": bars[-1]["c"], "prev_close": bars[-2]["c"],
                              "market_time": bars[-1]["t"], "fetched": 0, "source": "test"}
        r = trading_engine.snapshot("NIFTY", "1d", fetch=fake)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["data"]["last"], bars[-1]["c"])
        self.assertFalse(r["data"]["order_book"]["available"])
        bad = trading_engine.snapshot("NIFTY", "1d", fetch=lambda s, tf: {"ok": False, "error": "down"})
        self.assertFalse(bad["ok"])


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def _keys(self, **kw):
        base = {k: "" for k in ("JARVIS_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "JARVIS_OPENAI_API_KEY",
                                "OPENAI_API_KEY", "JARVIS_GROQ_API_KEY", "GROQ_API_KEY")}
        base.update(kw)
        return mock.patch.dict(os.environ, base)

    def test_plan_orders(self):
        with self._keys(JARVIS_GEMINI_API_KEY="g"), mock.patch.object(llm_router, "load_secrets"):
            self.assertEqual(llm_router.plan(self.root), ["gemini", "ollama"])
            self.assertEqual(llm_router.plan(self.root, cheap=True), ["ollama", "gemini"])
            cc_settings.save(self.root, {"ai_mode": "cloud_only"})
            self.assertEqual(llm_router.plan(self.root), ["gemini"])

    def test_cloud_failure_falls_back_to_local(self):
        with self._keys(JARVIS_GEMINI_API_KEY="g"), mock.patch.object(llm_router, "load_secrets"), \
                mock.patch.object(llm_router, "_gemini", side_effect=RuntimeError("HTTP 429")), \
                mock.patch.object(local_llm, "ready", return_value=True), \
                mock.patch.object(local_llm, "chat", return_value={"text": "local ok", "model": "jarvis-local", "seconds": 1}):
            r = llm_router.complete("hi", "", self.root)
        self.assertTrue(r["ok"])
        self.assertEqual(r["provider"], "ollama:jarvis-local")
        self.assertIn("gemini", r["errors"][0])

    def test_loopback_only(self):
        with mock.patch.dict(os.environ, {"JARVIS_OLLAMA_BASE": "http://evil.example:11434"}):
            self.assertEqual(local_llm.base_url(), "http://127.0.0.1:11434")
        with mock.patch.dict(os.environ, {"JARVIS_OLLAMA_BASE": "http://localhost:11500"}):
            self.assertEqual(local_llm.base_url(), "http://localhost:11500")

    def test_settings_live_trading_cannot_default_on(self):
        s = cc_settings.save(self.root, {"live_trading_enabled": "yes", "ai_mode": "bogus", "local_model": "bad model!"})
        self.assertFalse(s["live_trading_enabled"])
        self.assertEqual(s["ai_mode"], "hybrid")
        self.assertEqual(s["local_model"], "jarvis-local")
        self.assertIn("live_trading_enabled", cc_settings.FILE_ONLY_OFF_KEYS)


class MemoryQueueChainTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_memory_fts_and_reindex(self):
        (self.root / "memory").mkdir()
        (self.root / "memory" / "a.md").write_text("Banknifty expiry plan for Thursday", encoding="utf-8")
        m = memory_db.MemoryDB(self.root)
        self.assertEqual(m.reindex_files()["added"], 1)
        self.assertEqual(m.reindex_files()["added"], 0)
        m.add("note", "Ollama", "qwen local model runs on CPU")
        self.assertEqual(m.search("banknif")[0]["source"], "memory/a.md")
        self.assertEqual(m.search("qwen")[0]["title"], "Ollama")
        self.assertEqual(m.stats()["total"], 2)

    def test_queue_recovers_running_as_interrupted(self):
        q = task_queue.TaskQueue(self.root)
        t = q.add("chain", "x", {"topic": "x"})
        self.assertTrue(q.claim(t["id"]))
        q2 = task_queue.TaskQueue(self.root)  # "restart"
        self.assertEqual(q2.recover(), 1)
        self.assertEqual(q2.get(t["id"])["state"], "interrupted")
        self.assertTrue(q2.claim(t["id"]))

    def test_chain_writes_report_and_memory(self):
        q, m = task_queue.TaskQueue(self.root), memory_db.MemoryDB(self.root)
        calls = []

        def complete(prompt, system):
            calls.append(system[:20])
            return {"ok": True, "text": f"# Report\nstep {len(calls)} [1]", "provider": "fake"}

        search = lambda qy: {"ok": True, "data": {"results": [{"title": "Src", "url": "https://example.com/a", "snippet": "s"}]}}
        o = orchestrator.Orchestrator(self.root, q, m, complete=complete, search=search)
        r = o.submit("Nifty outlook")
        t = o.wait(r["data"]["id"], 10)
        self.assertEqual(t["state"], "done", t)
        self.assertEqual([s["agent"] for s in t["steps"]], ["research", "analyst", "writer"])
        body = (self.root / t["result"]).read_text(encoding="utf-8")
        self.assertIn("https://example.com/a", body)
        self.assertEqual(len(calls), 3)
        self.assertEqual(m.search("Nifty outlook")[0]["kind"], "report")

    def test_chain_refuses_and_cancels_on_stop(self):
        q, m = task_queue.TaskQueue(self.root), memory_db.MemoryDB(self.root)
        halted = {"v": False}
        gate = threading.Event()

        def complete(prompt, system):
            halted["v"] = True  # STOP pressed during step 1
            gate.set()
            return {"ok": True, "text": "x", "provider": "fake"}

        o = orchestrator.Orchestrator(self.root, q, m, is_halted=lambda: halted["v"], complete=complete,
                                      search=lambda qy: {"ok": False, "error": "offline"})
        r = o.submit("topic")
        t = o.wait(r["data"]["id"], 10)
        self.assertEqual(t["state"], "cancelled")
        self.assertFalse(o.submit("again")["ok"])


class TradingSafetyTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_paper_ledger_idempotent_long_only(self):
        led = paper_ledger.PaperLedger(self.root)
        a = led.place("NIFTY", "BUY", 2, 25000, client_order_id="c1")
        b = led.place("NIFTY", "BUY", 2, 25000, client_order_id="c1")
        self.assertTrue(b["duplicate"])
        self.assertFalse(led.place("NIFTY", "SELL", 5, 25100)["ok"])
        led.place("NIFTY", "SELL", 1, 25100)
        s = led.summary({"NIFTY": 25200})
        self.assertAlmostEqual(s["realized"], 100.0)
        self.assertAlmostEqual(s["positions"][0]["unrealized"], 200.0)
        self.assertEqual(a["data"]["id"][:6], "PAPER-")

    def test_live_gates_fail_closed(self):
        o = {"symbol": "NIFTY", "side": "BUY", "qty": 1}
        yes = lambda n: True
        self.assertEqual(broker_live.place_live_order(o, settings={}, halted=False, origin="ui", typed="R4 CONFIRM",
                                                      key_present=yes)["gate"], 1)
        on = {"live_trading_enabled": True}
        self.assertEqual(broker_live.place_live_order(o, settings=on, halted=True, origin="ui", typed="R4 CONFIRM")["gate"], 2)
        self.assertEqual(broker_live.place_live_order(o, settings=on, halted=False, origin="api", typed="R4 CONFIRM")["gate"], 3)
        self.assertEqual(broker_live.place_live_order(o, settings=on, halted=False, origin="ui", typed="confirm")["gate"], 4)
        r = broker_live.place_live_order(o, settings=on, halted=False, origin="ui", typed="R4 CONFIRM", key_present=yes)
        self.assertFalse(r["ok"])
        self.assertIn("nothing was sent", r["error"])


class KeysTests(unittest.TestCase):
    def test_set_key_validates_and_never_returns_value(self):
        store = {}
        fake = mock.MagicMock()
        fake.available.return_value = True
        fake.write.side_effect = lambda n, v: store.__setitem__(n, v) or True
        fake.read.side_effect = lambda n: store.get(n, "")
        fake.parse_env.return_value = []
        with tempfile.TemporaryDirectory() as td, mock.patch.object(keys_manager, "secrets_store", fake), \
                mock.patch.dict(os.environ, {}, clear=False):
            self.assertFalse(keys_manager.set_key(td, "bad", "x" * 20)["ok"])
            self.assertFalse(keys_manager.set_key(td, "JARVIS_API_TOKEN", "x" * 20)["ok"])
            self.assertFalse(keys_manager.set_key(td, "JARVIS_BROKER_SAHI_API_KEY", "has space inside")["ok"])
            r = keys_manager.set_key(td, "JARVIS_BROKER_SAHI_API_KEY", "s3cretvalue123")
            self.assertTrue(r["ok"])
            self.assertNotIn("s3cretvalue123", json.dumps(r))
            st = keys_manager.status(td)
            self.assertNotIn("s3cretvalue123", json.dumps(st))
            row = next(k for k in st["keys"] if k["name"] == "JARVIS_BROKER_SAHI_API_KEY")
            self.assertTrue(row["set"])
            keys_manager.set_key(td, "JARVIS_MYDATA_API_KEY", "abcdefgh12")
            self.assertIn("JARVIS_MYDATA_API_KEY", keys_manager.all_names(td))
            self.assertFalse(keys_manager.delete_key(td, "JARVIS_MYDATA_API_KEY")["ok"])
            os.environ.pop("JARVIS_BROKER_SAHI_API_KEY", None)
            os.environ.pop("JARVIS_MYDATA_API_KEY", None)


class _FakeBridge:
    def __init__(self):
        self.halted = False
        self.stops = []

    def _stopped(self):
        return self.halted

    def halt_stop(self, src, reason):
        self.halted = True
        self.stops.append(src)
        return {"ok": True, "data": {"stopped": True}}

    def api_status(self):
        return {"ok": True, "data": {"halted": self.halted}}

    def ask(self, text, local=False):
        return {"ok": True, "data": {"text": "answer:" + text, "provider": "fake"}}

    def memory_search(self, q, limit=20):
        return {"ok": True, "data": {"results": [], "q": q}}


class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.b = _FakeBridge()
        import socket

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.api = jarvis_api.LocalApi(self.b, port=self.port, token_fn=lambda: "tok-123")
        self.assertTrue(self.api.start()["ok"])

    def tearDown(self):
        self.api.stop()

    def _req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Authorization": "Bearer tok-123", "Content-Type": "application/json"}
        h.update(headers or {})
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        return r.status, json.loads(r.read() or b"{}")

    def test_auth_origin_host(self):
        self.assertEqual(self._req("GET", "/v1/status", headers={"Authorization": "Bearer nope"})[0], 401)
        self.assertEqual(self._req("GET", "/v1/status", headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self._req("GET", "/v1/status", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self._req("GET", "/v1/status")[0], 200)

    def test_ask_and_listing(self):
        st, r = self._req("POST", "/v1/ask", {"text": "hello"})
        self.assertEqual((st, r["data"]["text"]), (200, "answer:hello"))
        st, r = self._req("GET", "/v1")
        self.assertTrue(any(e["path"] == "/v1/chain" for e in r["data"]))

    def test_stop_blocks_api_and_resume_refused(self):
        self.assertEqual(self._req("POST", "/v1/stop", {"reason": "test"})[0], 200)
        self.assertEqual(self.b.stops, ["api"])
        self.assertEqual(self._req("POST", "/v1/ask", {"text": "x"})[0], 423)
        self.assertEqual(self._req("GET", "/v1/memory/search?q=a")[0], 423)
        self.assertEqual(self._req("GET", "/v1/status")[0], 200)
        self.assertEqual(self._req("POST", "/v1/resume", {})[0], 403)

    def test_no_token_store_no_api(self):
        a = jarvis_api.LocalApi(self.b, port=self.port + 1, token_fn=lambda: "")
        self.assertFalse(a.start()["ok"])


if __name__ == "__main__":
    unittest.main()
