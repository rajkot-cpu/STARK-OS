"""Real-browser check that the 3D orbit canvases keep a stable size on HiDPI (125%/150%) screens.

Needs node, Chrome and playwright-core; set JARVIS_PLAYWRIGHT_DIR to a folder whose node_modules has
playwright-core (and optionally JARVIS_CHROME). Skipped otherwise.
"""
import os
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PW = os.environ.get("JARVIS_PLAYWRIGHT_DIR", "")
CHROME = os.environ.get("JARVIS_CHROME") or shutil.which("google-chrome") or shutil.which("chromium") or ""


@unittest.skipUnless(shutil.which("node") and CHROME and PW and (Path(PW) / "node_modules" / "playwright-core").is_dir(),
                     "node + chrome + playwright-core (JARVIS_PLAYWRIGHT_DIR) needed")
class OrbitHiDpiBrowserTest(unittest.TestCase):
    def test_canvases_do_not_grow(self):
        r = subprocess.run(["node", str(HERE / "js" / "orbit_hidpi.browser.mjs"), str(HERE.parent / "ui"), PW, CHROME],
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
