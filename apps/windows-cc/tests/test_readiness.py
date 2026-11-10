# apps/windows-cc/tests/test_readiness.py
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "windows-cc"))
sys.path.insert(0, str(ROOT / "apps" / "windows-panel"))
sys.path.insert(0, str(ROOT / "scripts" / "win"))

from readiness import CHECKS, compute_readiness

SECRET = "sk-proj-TEST-LEAK-ME-NEVER-1234567890abcdef"
GEMINI_SECRET = "AIzaSy-TEST-LEAK-ME-NEVER-gemini"


def _write_policy(root: Path, *, approved: bool = True, placeholders: bool = False) -> None:
    status = "approved" if approved else "draft"
    if placeholders:
        restricted = (
            "  - ~/patients\n"
            "  - PLACEHOLDER_patient_records_path\n"
            "  - PLACEHOLDER_banking_brokerage_path\n"
            "  - PLACEHOLDER_tax_legal_path\n"
        )
    else:
        restricted = "  - C:\\\\Users\\\\chandan\\\\patients\n  - C:\\\\Users\\\\chandan\\\\finance\n"
    (root / "POLICY.yaml").write_text(
        f"status: {status}\nrestricted:\n{restricted}schedule:\n  quiet_hours: \"00:00-00:00\"\n",
        encoding="utf-8",
    )


def _write_secrets(root: Path, mapping: dict[str, str]) -> None:
    d = root / "secrets"
    d.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in mapping.items()]
    (d / "api_keys.env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _full_root(tmp: Path) -> Path:
    (tmp / "STATE.md").write_text("# STATE\n", encoding="utf-8")
    (tmp / "logs").mkdir(exist_ok=True)
    _write_policy(tmp, approved=True, placeholders=False)
    _write_secrets(
        tmp,
        {
            "JARVIS_OPENAI_API_KEY": SECRET,
            "JARVIS_GEMINI_API_KEY": GEMINI_SECRET,
        },
    )
    return tmp


class TestReadinessScoring(unittest.TestCase):
    def setUp(self):
        from llm_providers import clear_cached_probes

        clear_cached_probes()

    def test_weights_sum_to_100(self):
        self.assertEqual(sum(c["weight"] for c in CHECKS), 100)
        ids = [c["id"] for c in CHECKS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_present_scores_100(self):
        with tempfile.TemporaryDirectory() as td:
            root = _full_root(Path(td))
            out = compute_readiness(
                root,
                env={},
                probes=[{"id": "openai", "state": "connected"}],
                stt_ok=True,
                tts_ok=True,
            )
            self.assertEqual(out["score_pct"], 100)
            self.assertTrue(all(c["ok"] for c in out["checks"]))
            self.assertEqual(len(out["checks"]), len(CHECKS))

    def test_none_configured_scores_low(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # A regular file named logs makes the audit-log check fail too.
            (root / "logs").write_text("not a directory", encoding="utf-8")
            out = compute_readiness(
                root,
                env={},
                probes=None,
                stt_ok=False,
                tts_ok=False,
                agents_ok=False,
            )
            self.assertLess(out["score_pct"], 40)
            self.assertGreaterEqual(out["score_pct"], 0)
            self.assertFalse(any(c["ok"] for c in out["checks"]))
            self.assertEqual(out["score_pct"], 0)

    def test_score_is_sum_of_ok_weights(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "STATE.md").write_text("# STATE\n", encoding="utf-8")
            _write_policy(root, approved=True, placeholders=True)
            _write_secrets(root, {"JARVIS_OPENAI_API_KEY": SECRET})
            (root / "logs").mkdir()
            out = compute_readiness(
                root,
                env={},
                probes=None,
                stt_ok=False,
                tts_ok=False,
            )
            expected = sum(c["weight"] for c in out["checks"] if c["ok"])
            self.assertEqual(out["score_pct"], expected)
            by_id = {c["id"]: c for c in out["checks"]}
            self.assertTrue(by_id["llm_any_key"]["ok"])
            self.assertTrue(by_id["openai_key"]["ok"])
            self.assertFalse(by_id["gemini_key"]["ok"])
            self.assertTrue(by_id["llm_reachable"]["ok"])  # no cache: key presence only
            self.assertTrue(by_id["policy_ok"]["ok"])
            self.assertFalse(by_id["policy_paths"]["ok"])
            self.assertTrue(by_id["secrets_file"]["ok"])
            self.assertTrue(by_id["audit_log"]["ok"])

    def test_cached_failed_probe_is_not_reachable(self):
        with tempfile.TemporaryDirectory() as td:
            root = _full_root(Path(td))
            out = compute_readiness(
                root,
                env={},
                probes=[{"id": "openai", "state": "auth_error"}],
                stt_ok=True,
                tts_ok=True,
            )
            by_id = {c["id"]: c for c in out["checks"]}
            self.assertFalse(by_id["llm_reachable"]["ok"])
            self.assertEqual(out["score_pct"], 100 - by_id["llm_reachable"]["weight"])

    def test_no_secret_leak(self):
        with tempfile.TemporaryDirectory() as td:
            root = _full_root(Path(td))
            out = compute_readiness(
                root,
                env={"JARVIS_GROQ_API_KEY": "gsk-LEAK-THIS-VALUE-TOO"},
                probes=[{"id": "openai", "state": "connected", "detail": "http 200"}],
                stt_ok=True,
                tts_ok=True,
            )
            blob = json.dumps(out)
            self.assertNotIn(SECRET, blob)
            self.assertNotIn(GEMINI_SECRET, blob)
            self.assertNotIn("gsk-LEAK-THIS-VALUE-TOO", blob)
            self.assertNotIn("LEAK", blob)
            for c in out["checks"]:
                self.assertIsInstance(c["ok"], bool)
                self.assertIn("id", c)
                self.assertIn("label", c)
                self.assertIn("weight", c)
                self.assertIn("fix", c)
                self.assertIsInstance(c["fix"], str)

    def test_fix_text_is_user_facing(self):
        with tempfile.TemporaryDirectory() as td:
            out = compute_readiness(Path(td), env={}, stt_ok=False, tts_ok=False, agents_ok=False)
            by_id = {c["id"]: c for c in out["checks"]}
            self.assertIn("Gemini", by_id["gemini_key"]["fix"])
            self.assertIn("API Keys", by_id["gemini_key"]["fix"])
            self.assertNotIn("JARVIS_GEMINI_API_KEY", by_id["gemini_key"]["fix"])

    def test_bridge_readiness_shape(self):
        from bridge_api import BridgeApi

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "STATE.md").write_text("# STATE\n", encoding="utf-8")
            _write_policy(root, approved=True, placeholders=False)
            (root / "logs").mkdir()
            api = BridgeApi(root=root)
            out = api.readiness()
            self.assertTrue(out["ok"])
            data = out["data"]
            self.assertIn("score_pct", data)
            self.assertIn("checks", data)
            self.assertIsInstance(data["score_pct"], int)
            self.assertGreaterEqual(data["score_pct"], 0)
            self.assertLessEqual(data["score_pct"], 100)


if __name__ == "__main__":
    unittest.main()
