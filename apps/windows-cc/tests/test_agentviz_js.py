"""Runs the pure-JS tests for the 3D agent orbit (ui/js/agentviz.js) with node, when available."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AgentVizJsTest(unittest.TestCase):
    def test_node_suite(self):
        r = subprocess.run(["node", "--test", str(HERE / "js" / "agentviz.test.mjs")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
