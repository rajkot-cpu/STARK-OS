# apps/windows-room/tests/test_ui_contract.py
"""Static checks: vendored three.js, voice does not speak the transcript, exe name."""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROOM = ROOT / "apps" / "windows-room"
UI = ROOM / "ui"
VENDOR_3D = ROOT / "apps" / "windows-3d" / "ui" / "vendor"


class TestUiContract(unittest.TestCase):
    def test_vendor_matches_windows_3d_three(self):
        for name in ("three.module.min.js", "CSS2DRenderer.js", "OrbitControls.js"):
            room_bytes = (UI / "vendor" / name).read_bytes()
            desk_bytes = (VENDOR_3D / name).read_bytes()
            self.assertGreater(len(room_bytes), 1000, name)
            self.assertEqual(
                hashlib.sha256(room_bytes).hexdigest(),
                hashlib.sha256(desk_bytes).hexdigest(),
                name,
            )
        css2d = (UI / "vendor" / "CSS2DRenderer.js").read_text(encoding="utf-8")
        orbit = (UI / "vendor" / "OrbitControls.js").read_text(encoding="utf-8")
        self.assertIn("./three.module.min.js", css2d)
        self.assertIn("./three.module.min.js", orbit)
        self.assertNotIn("https://", css2d)
        self.assertNotIn("https://", orbit)

    def test_scene_uses_orbit_and_css2d(self):
        scene = (UI / "js" / "scene.js").read_text(encoding="utf-8")
        self.assertIn('from "../vendor/three.module.min.js"', scene)
        self.assertIn("OrbitControls", scene)
        self.assertIn("CSS2DRenderer", scene)
        self.assertIn("CSS2DObject", scene)
        self.assertNotIn("unpkg.com", scene)
        self.assertNotIn("cdn", scene.lower())

    def test_voice_speaks_reply_not_transcript(self):
        app = (UI / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("voice_turn", app)
        self.assertRegex(app, r'call\(\s*"chat"')
        speaks = re.findall(r'call\(\s*"speak"\s*,\s*([^)]+)\)', app)
        self.assertTrue(speaks, "voice path must speak the model reply")
        for arg in speaks:
            self.assertIn(arg.strip(), {"reply", "r.reply"})
        self.assertNotIn("speak\", r.text", app)
        self.assertNotIn("speak(r.text", app)

    def test_build_script_names_room_exe_only(self):
        text = (ROOM / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn("--name JarvisRoom", text)
        self.assertIn("JarvisRoom.exe", text)
        self.assertNotIn("Jarvis3D", text)
        stripped = text.replace("JarvisRoom.exe", "").replace("JarvisRoom", "")
        self.assertNotIn("Jarvis.exe", stripped)
        self.assertIn("--hidden-import bridge_api", text)
        self.assertIn("windows-cc", text)

    def test_host_does_not_reimplement_bridge(self):
        host = (ROOM / "host_main.py").read_text(encoding="utf-8")
        room = (ROOM / "room_api.py").read_text(encoding="utf-8")
        self.assertIn("make_api", host)
        self.assertNotIn("class BridgeApi", host)
        self.assertNotIn("class BridgeApi", room)
        self.assertIn("windows-cc", room)
        self.assertFalse((ROOM / "bridge_api.py").exists())


if __name__ == "__main__":
    unittest.main()
