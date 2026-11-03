# JarvisRoom (Phase 1)
Three.js holographic workshop (desk + 4 floating plates: Status, Voice, Agents/LLMs, Live Feed) over the Command Center `BridgeApi` (imported from `../windows-cc` via sys.path). Three.js r170 vendored in `ui/vendor/` (offline).

Run: `pip install -r requirements.txt && JARVIS_HOME=/path/to/jarvis python host_main.py`
Test: `python -m unittest discover -s apps/windows-room/tests -v`
