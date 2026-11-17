"""UI v3 restyle: real-data helpers behind the new HUD panels (no fake numbers)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))
UI = ROOT / "apps" / "windows-cc" / "ui"


class MetricsV3(unittest.TestCase):
    def test_snapshot_has_gb_net_uptime(self):
        import metrics

        m = metrics.snapshot()
        for k in ("cpu_pct", "ram_pct", "disk_pct", "ram_used_gb", "ram_total_gb", "net_bps", "uptime_s", "proc_rss_mb"):
            self.assertIn(k, m)
        self.assertGreater(m["ram_total_gb"], 0)
        self.assertLessEqual(m["ram_used_gb"], m["ram_total_gb"])
        self.assertGreaterEqual(m["uptime_s"], 0)

    def test_net_rate_is_none_on_first_sample_then_delta(self):
        import metrics

        metrics._NET.clear()
        Snap = type("C", (), {})
        a, b = Snap(), Snap()
        a.bytes_sent, a.bytes_recv = 1000, 1000
        b.bytes_sent, b.bytes_recv = 1500, 3500
        with mock.patch("metrics.psutil.net_io_counters", side_effect=[a, b]), \
             mock.patch("metrics.time.monotonic", side_effect=[10.0, 12.0]):
            self.assertIsNone(metrics._net_rate())
            self.assertEqual(metrics._net_rate(), 1500.0)


class MemoryIndexV3(unittest.TestCase):
    def test_counts_per_source_and_recent_files(self):
        from memory_index import build

        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / "memory").mkdir()
            (r / "memory" / "preferences.md").write_text("x", encoding="utf-8")
            (r / "reports").mkdir()
            (r / "reports" / "2026-11-10.md").write_text("yy", encoding="utf-8")
            (r / "STATE.md").write_text("z", encoding="utf-8")
            d = build(r)
            self.assertEqual(d["nodes"], 3)
            self.assertEqual(d["by_source"], {"STATE.md": 1, "memory": 1, "reports": 1})
            self.assertEqual(d["bytes"], 4)
            self.assertEqual(sorted(d["recent"]), ["2026-11-10.md", "STATE.md", "preferences.md"])
            self.assertEqual(d["candidates"], 5)

    def test_empty_root(self):
        from memory_index import build

        with tempfile.TemporaryDirectory() as td:
            d = build(Path(td))
            self.assertEqual((d["nodes"], d["by_source"], d["recent"]), (0, {}, []))


class LocalAiAndSources(unittest.TestCase):
    def test_ollama_not_installed(self):
        import ui_sources

        with mock.patch("ui_sources._ollama_exe", return_value=None):
            d = ui_sources.local_ai()
        self.assertEqual(d["ollama"]["state"], "not_installed")
        self.assertEqual(d["ollama"]["models"], [])

    def test_ollama_installed_no_models(self):
        import ui_sources

        with mock.patch("ui_sources._ollama_exe", return_value="C:/x/ollama.exe"), \
             mock.patch("ui_sources._tags", return_value={"models": []}):
            d = ui_sources.local_ai()
        self.assertEqual(d["ollama"]["state"], "no_models")

    def test_ollama_installed_not_running(self):
        import ui_sources

        with mock.patch("ui_sources._ollama_exe", return_value="C:/x/ollama.exe"), \
             mock.patch("ui_sources._tags", return_value=None):
            self.assertEqual(ui_sources.local_ai()["ollama"]["state"], "not_running")

    def test_ollama_models_listed(self):
        import ui_sources

        with mock.patch("ui_sources._ollama_exe", return_value="C:/x/ollama.exe"), \
             mock.patch("ui_sources._tags", return_value={"models": [{"name": "qwen2.5:3b"}]}):
            d = ui_sources.local_ai()["ollama"]
        self.assertEqual((d["state"], d["models"]), ("ready", ["qwen2.5:3b"]))

    def test_data_sources_market_never_connected(self):
        import ui_sources

        with tempfile.TemporaryDirectory() as td:
            rows = ui_sources.data_sources(Path(td))
        ids = [r["id"] for r in rows]
        self.assertEqual(ids, ["web_search", "memory", "files", "mcp", "market_data"])
        market = rows[-1]
        self.assertEqual(market["state"], "not_connected")
        for r in rows:
            self.assertIn(r["state"], {"connected", "not_connected", "empty", "unavailable"})

    def test_bridge_calls(self):
        from bridge_api import BridgeApi

        with tempfile.TemporaryDirectory() as td:
            api = BridgeApi.__new__(BridgeApi)
            api.root = Path(td)
            with mock.patch("ui_sources._ollama_exe", return_value=None):
                self.assertTrue(api.local_ai()["ok"])
            r = api.sources()
            self.assertTrue(r["ok"])
            self.assertEqual(r["data"]["sources"][-1]["id"], "market_data")
            info = api.app_info()["data"]
            self.assertEqual(info["operator"], "Dr. Chandan Kumar")
            self.assertTrue(info["version"])


class UiV3Static(unittest.TestCase):
    def setUp(self):
        self.html = (UI / "index.html").read_text(encoding="utf-8")
        self.js = "\n".join(p.read_text(encoding="utf-8") for p in (UI / "js").glob("*.js"))

    def test_estop_stays_in_topbar(self):
        top = self.html.split('<header class="topbar"', 1)[1].split("</header>", 1)[0]
        self.assertIn('id="btn-estop"', top)
        self.assertIn("EMERGENCY STOP", top)

    def test_new_pages_and_nav(self):
        for route in ("home", "core", "agents", "tasks", "calendar", "memory", "conversations", "knowledge",
                      "skills", "workflows", "security", "trading", "safety", "settings"):
            self.assertIn(f'data-route="{route}"', self.html)
            self.assertIn(f'id="page-{route}"', self.html)

    def test_trading_is_paper_only_and_has_no_order_calls(self):
        page = self.html.split('id="page-trading"', 1)[1].split("</section>", 1)[0]
        self.assertIn("PAPER", page)
        self.assertIn("no live orders", page)
        low = self.js.lower()
        for bad in ("place_order", "submit_order", "live_trade(", "call(\"order", "call('order"):
            self.assertNotIn(bad, low)

    def test_operator_name(self):
        self.assertIn("Dr. Chandan Kumar", self.html)

    def test_phase1_ids_kept(self):
        for i in ("halt-banner", "hb-resume", "sf-stop", "sf-resume", "sf-verify", "resume-modal", "sf-levels"):
            self.assertIn(f'id="{i}"', self.html)



class OpenFolderRelative(unittest.TestCase):
    def test_relative_workspace_resolves_under_root(self):
        from bridge_api import BridgeApi

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "workspace").mkdir()
            api = BridgeApi.__new__(BridgeApi)
            api.root = Path(td)
            with mock.patch("os.startfile", create=True) as sf:
                r = api.open_folder("workspace")
            self.assertTrue(r["ok"], r)
            sf.assert_called_once()
            with mock.patch("os.startfile", create=True):
                self.assertFalse(api.open_folder("..")["ok"])


if __name__ == "__main__":
    unittest.main()
