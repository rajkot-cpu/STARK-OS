"""Phase 1 (Master Upgrade Module 1): Emergency STOP, audit chain, secrets store, session log,
permission levels. Runs on Linux and Windows."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
for p in ("apps/windows-cc", "apps/windows-panel", "scripts/win"):
    sys.path.insert(0, str(ROOT / p))

import audit_chain  # noqa: E402
import cc_settings  # noqa: E402
import halt  # noqa: E402
import hotkey_win  # noqa: E402
import permissions  # noqa: E402
import secrets_store  # noqa: E402
import session_log  # noqa: E402
from agents.worker import AgentHub  # noqa: E402
from bridge_api import BridgeApi  # noqa: E402
from voice_intents import match  # noqa: E402


def _api(d):
    api = BridgeApi.__new__(BridgeApi)
    api.root = Path(d)
    api._hub = AgentHub(root=Path(d), gemini_key="g")
    api._hub.on_event = None
    api._hub.halted = lambda: api._stopped()
    api.speak = mock.Mock(return_value={"ok": True})
    return api


def _block_run(hub, role):
    """Make a role 'run' until its stop flag is set (stand-in for a long agent job)."""
    started = threading.Event()

    def fake_run(role_id, saved=None):
        started.set()
        hub._stop[role_id].wait(10)
        hub._state[role_id] = "standby"

    hub._run = fake_run
    return started


class HaltControllerTests(unittest.TestCase):
    def tearDown(self):
        halt.set_current(None)

    def test_stop_persists_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            self.assertFalse(c.is_stopped())
            c.stop("button", "test")
            self.assertTrue(c.is_stopped())
            c2 = halt.HaltController(d)  # e.g. Jarvis restarted
            self.assertTrue(c2.is_stopped(), "STOP must not clear itself on restart")
            self.assertEqual(c2.status()["source"], "button")

    def test_resume_needs_typed_word(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            c.stop("button")
            self.assertFalse(c.resume("button", "")["ok"])
            self.assertFalse(c.resume("button", "yes")["ok"])
            self.assertTrue(c.is_stopped())
            self.assertTrue(c.resume("button", "resume")["ok"])
            self.assertFalse(c.is_stopped())

    def test_stop_file_triggers_and_blocks_resume(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            ran = []
            c.on_stop("probe", lambda: ran.append(1))
            (Path(d) / "STOP").write_text("")
            self.assertTrue(c.check_once())
            self.assertEqual(ran, [1])
            self.assertEqual(c.status()["source"], "stop_file")
            r = c.resume("button", "RESUME")
            self.assertFalse(r["ok"])
            self.assertIn("STOP file", r["error"])
            (Path(d) / "STOP").unlink()
            self.assertTrue(c.resume("button", "RESUME")["ok"])

    def test_watcher_reacts_within_seconds(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            c.start_watch(0.1)
            try:
                (Path(d) / "STOP").write_text("")
                t0 = time.time()
                while not c.status().get("since") and time.time() - t0 < 3:
                    time.sleep(0.05)
                self.assertEqual(c.status()["source"], "stop_file")
            finally:
                c.stop_watch()

    def test_failing_handler_does_not_block_others(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            ran = []
            c.on_stop("bad", lambda: 1 / 0)
            c.on_stop("good", lambda: ran.append("ok"))
            r = c.stop("button")
            self.assertEqual(ran, ["ok"])
            self.assertIn("error", r["data"]["report"]["bad"])

    def test_stop_and_resume_are_audited(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            c.stop("hotkey", "x")
            c.resume("button", "RESUME")
            text = (Path(d) / "logs" / "audit.jsonl").read_text()
            self.assertIn("emergency_stop", text)
            self.assertIn('"resume"', text)
            self.assertTrue(audit_chain.verify(Path(d) / "logs" / "audit.jsonl")["ok"])

    def test_stop_kills_tracked_child_process(self):
        with tempfile.TemporaryDirectory() as d:
            c = halt.HaltController(d)
            halt.set_current(c)
            out = {}

            def run():
                try:
                    out["r"] = halt.run_tracked([sys.executable, "-c", "import time; time.sleep(30)"],
                                                capture_output=True, text=True, timeout=60)
                except Exception as e:  # pragma: no cover
                    out["e"] = e

            t = threading.Thread(target=run)
            t0 = time.time()
            t.start()
            time.sleep(0.5)
            r = c.stop("button")
            t.join(10)
            self.assertFalse(t.is_alive())
            self.assertLess(time.time() - t0, 10)
            self.assertGreaterEqual(r["data"]["report"]["child_processes_killed"], 1)
            with self.assertRaises(halt.HaltedError):
                halt.run_tracked([sys.executable, "-c", "pass"])


class BridgeStopTests(unittest.TestCase):
    def tearDown(self):
        halt.set_current(None)

    def test_typed_stop_halts_running_agent_and_blocks_new_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            started = _block_run(api._hub, "research")
            self.assertTrue(api.agent_start("research", "long job")["ok"])
            self.assertTrue(started.wait(3))
            r = api.command("Jarvis stop")
            self.assertEqual(r["data"]["routed"], "halt")
            self.assertTrue(api._hub._stop["research"].is_set())
            self.assertEqual(api._hub._state["research"], "standby")
            self.assertTrue(api.status()["data"]["halted"] if api.status()["ok"] else api._stopped())
            # new work is refused everywhere
            self.assertTrue(api.agent_start("builder", "x").get("halted"))
            self.assertFalse(api.command("build me a snake game")["data"]["started"])
            self.assertTrue(api.shell_confirm("dir").get("halted"))
            self.assertTrue(api.tool_confirm("research", "t").get("halted"))
            self.assertTrue(api.screen_read("q", confirmed=True).get("halted"))
            self.assertTrue(api.start_workday(confirmed=True).get("halted"))
            self.assertTrue(api._hub.start("coding", "x").get("halted"))

    def test_stop_cancels_pending_r3_requests(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            api._hub._pending["coding"] = {"token": "t", "kind": "mcp"}
            api._hub._halted["coding"] = {"call": {}}
            api.halt_stop("button")
            self.assertNotIn("coding", api._hub._pending)
            self.assertNotIn("coding", api._hub._halted)

    def test_no_auto_resume_and_typed_resume_works(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            started = _block_run(api._hub, "video")
            api.agent_start("video", "make a short")
            started.wait(3)
            api.halt_stop("button")
            time.sleep(0.3)
            r = api.command("resume")
            self.assertTrue(r["data"]["resumed"])
            self.assertFalse(api._stopped())
            self.assertEqual(api._hub._state["video"], "standby", "stopped work must not restart")
            self.assertTrue(api.agent_start("video", "again")["ok"])
            api._hub.stop("video")

    def test_voice_cannot_resume(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            api.halt_stop("button")
            r = api._route("Jarvis resume", speak=True)
            self.assertFalse(r["data"]["resumed"])
            self.assertTrue(api._stopped())

    def test_resume_refused_while_stop_file_exists(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            (Path(d) / "STOP").write_text("")
            self.assertTrue(api._stopped())
            self.assertFalse(api.halt_resume("RESUME")["ok"])
            self.assertFalse(api.command("resume")["data"]["resumed"])

    def test_ui_cannot_switch_off_stop_triggers(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            api.settings_set({"stop_hotkey": False, "stop_file_watch": False})
            s = cc_settings.load(d)
            self.assertTrue(s["stop_hotkey"])
            self.assertTrue(s["stop_file_watch"])

    def test_trading_stays_reserved(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            r = api.command("start trading")
            self.assertEqual(r["data"]["routed"], "start_trading")
            self.assertIn("No trading was started", r["data"]["reply"])
            rep = api.halt_stop("button")["data"]["report"]
            self.assertIn("no trading module", rep["trading"])

    def test_halt_status_and_safety_info(self):
        with tempfile.TemporaryDirectory() as d:
            api = _api(d)
            st = api.halt_status()["data"]
            self.assertFalse(st["stopped"])
            self.assertTrue(st["stop_file"].endswith("STOP"))
            info = api.safety_info()
            self.assertTrue(info["ok"], info)
            self.assertEqual([l["tier"] for l in info["data"]["levels"]], ["R1", "R2", "R3", "R4"])


class IntentTests(unittest.TestCase):
    def test_halt_phrases(self):
        for t in ("stop", "Jarvis stop", "jarvis, stop everything", "emergency stop", "STOP!",
                  "stop all agents", "halt now"):
            self.assertEqual(match(t)["intent"], "halt", t)

    def test_not_halt(self):
        self.assertEqual(match("stop builder")["intent"], "stop_agent")
        self.assertEqual(match("stop trading")["intent"], "stop_trading")
        self.assertEqual(match("build a stop watch app")["intent"], "agent")
        self.assertEqual(match("resume")["intent"], "resume")
        self.assertEqual(match("resume trading")["intent"], "start_trading")


class AuditChainTests(unittest.TestCase):
    def test_chain_detects_edit_and_delete(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "logs" / "audit.jsonl"
            p.parent.mkdir()
            p.write_text('{"time":"old","action":"legacy"}\n')  # pre-upgrade line
            for i in range(4):
                cc_settings.audit(d, "t", f"a{i}", "r")
            with p.open("a") as f:  # another tool writes a plain line; still fine
                f.write('{"time":"x","action":"panel"}\n')
            cc_settings.audit(d, "t", "a4", "r")
            v = audit_chain.verify(p)
            self.assertTrue(v["ok"], v)
            self.assertEqual(v["chained"], 5)
            lines = p.read_text().splitlines()
            edited = lines[:]
            edited[2] = edited[2].replace('"r"', '"R"')
            p.write_text("\n".join(edited) + "\n")
            self.assertFalse(audit_chain.verify(p)["ok"])
            p.write_text("\n".join(lines[:1] + lines[2:]) + "\n")  # delete a line
            self.assertFalse(audit_chain.verify(p)["ok"])
            p.write_text("\n".join(lines[:1] + ['{"action":"legacy-edit"}'] + lines[2:]) + "\n")
            self.assertFalse(audit_chain.verify(p)["ok"])

    def test_cli_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            cc_settings.audit(d, "t", "a", "r")
            p = Path(d) / "logs" / "audit.jsonl"
            r = subprocess.run([sys.executable, str(ROOT / "apps/windows-cc/audit_chain.py"), str(p)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class FakeStore:
    def __init__(self, fail=()):
        self.d, self.fail = {}, set(fail)

    def write(self, k, v):
        if k in self.fail:
            return False
        self.d[k] = v
        return True

    def read(self, k):
        return self.d.get(k, "")


class SecretsStoreTests(unittest.TestCase):
    def _env(self, d, text):
        p = Path(d) / "secrets" / "api_keys.env"
        p.parent.mkdir()
        p.write_text(text)
        return p

    def test_not_windows_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "JARVIS_GROQ_API_KEY=gsk_x\n")
            with mock.patch.object(secrets_store, "available", return_value=False):
                r = secrets_store.migrate(d)
            self.assertFalse(r["ok"])
            self.assertEqual(p.read_text(), "JARVIS_GROQ_API_KEY=gsk_x\n")

    def test_migrate_verifies_then_strips_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._env(d, "# keys\nJARVIS_GROQ_API_KEY=gsk_secret1\nJARVIS_GEMINI_API_KEY='AIza2'\n")
            fs = FakeStore()
            with mock.patch.object(secrets_store, "available", return_value=True), \
                 mock.patch.object(secrets_store, "write", fs.write), \
                 mock.patch.object(secrets_store, "read", fs.read):
                r = secrets_store.migrate(d)
                self.assertTrue(r["ok"], r)
                text = p.read_text()
                self.assertNotIn("gsk_secret1", text)
                self.assertNotIn("AIza2", text)
                self.assertEqual(sorted(secrets_store.migrated_names(d)),
                                 ["JARVIS_GEMINI_API_KEY", "JARVIS_GROQ_API_KEY"])
                with mock.patch.dict(os.environ, {}, clear=True):
                    import llm_providers

                    llm_providers.load_secrets(Path(d))
                    self.assertEqual(os.environ.get("JARVIS_GROQ_API_KEY"), "gsk_secret1")
                st = secrets_store.status(d)
                self.assertEqual(st["plaintext_keys_in_file"], [])
                self.assertNotIn("gsk_secret1", json.dumps(st))

    def test_any_failure_keeps_file(self):
        with tempfile.TemporaryDirectory() as d:
            orig = "JARVIS_GROQ_API_KEY=a\nJARVIS_OPENAI_API_KEY=b\n"
            p = self._env(d, orig)
            fs = FakeStore(fail={"JARVIS_OPENAI_API_KEY"})
            with mock.patch.object(secrets_store, "available", return_value=True), \
                 mock.patch.object(secrets_store, "write", fs.write), \
                 mock.patch.object(secrets_store, "read", fs.read):
                r = secrets_store.migrate(d)
            self.assertFalse(r["ok"])
            self.assertEqual(p.read_text(), orig)


class SessionLogTests(unittest.TestCase):
    def test_unclean_previous_session_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            logs = []
            s1 = session_log.SessionLog(d, log=lambda *a: logs.append(a))
            self.assertIsNone(s1.start())
            # no end() -> simulate crash
            s2 = session_log.SessionLog(d, log=lambda *a: logs.append(a))
            prev = s2.start()
            self.assertIsNotNone(prev)
            self.assertTrue(any("without a clean exit" in a[2] for a in logs))
            s2.end("window closed")
            s3 = session_log.SessionLog(d, log=lambda *a: logs.append(a))
            self.assertIsNone(s3.start())


class PermissionTests(unittest.TestCase):
    def test_mapping_never_weakens(self):
        self.assertEqual(permissions.tier_for("live_trade"), "R4")
        self.assertEqual(permissions.tier_for("unknown_new_action"), "R4")
        self.assertEqual(permissions.tier_for("shell_other"), "R3")
        self.assertEqual(permissions.tier_for("mcp_tool"), "R3")
        self.assertEqual(permissions.tier_for("screen_read"), "R3")
        self.assertEqual(permissions.tier_for("read_file"), "R1")


class HotkeyTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(hotkey_win.parse("Ctrl+Alt+Shift+S"),
                         (hotkey_win.MOD_CONTROL | hotkey_win.MOD_ALT | hotkey_win.MOD_SHIFT, ord("S")))
        self.assertIsNone(hotkey_win.parse("S"))
        self.assertIsNone(hotkey_win.parse("Ctrl+Banana"))

    @unittest.skipIf(os.name == "nt", "non-Windows path")
    def test_unsupported_off_windows(self):
        self.assertEqual(hotkey_win.GlobalHotkey(lambda: None).start(), "unsupported")


if __name__ == "__main__":
    unittest.main()
