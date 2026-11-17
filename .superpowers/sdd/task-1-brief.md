# Task brief (extracted)

## Global Constraints

- Local only — no Grok Bot bridge in v1.
- Standalone `.exe` for end user (no Python required after freeze).
- Stark HUD: dark background, cyan accents, gold highlights.
- Never write outside JARVIS_ROOT except allowlisted app launches.
- R3 in-app confirm before POLICY save, workday (non-dry), write/launch skills, app launch.
- `block_delete` remains authoritative; panel never bypasses it.
- Audit every write/launch/refusal via JSONL under `logs/`.
- Default root: `C:\Users\rajk1\jarvis`; override via `JARVIS_HOME` env for tests.
- STATE tab is read-only in v1.
- Windows apps map for v1: `chrome` → `chrome.exe` (or Program Files path), `terminal` → `wt.exe` then `powershell.exe`.


---

### Task 1: JARVIS_HOME override + panel_api root discovery

**Files:**
- Modify: `scripts/win/lib_jarvis.py`
- Create: `apps/windows-panel/panel_api.py`
- Create: `apps/windows-panel/tests/test_panel_api.py`
- Create: `apps/windows-panel/requirements.txt`

**Interfaces:**
- Consumes: existing `lib_jarvis.jarvis_home`, `append_audit`, `quiet_hours_active`, `load_policy`
- Produces:
  - `jarvis_home() -> Path` respects `os.environ["JARVIS_HOME"]` if set and valid
  - `panel_api.is_valid_root(path: Path) -> bool` — true iff `STATE.md` and `POLICY.yaml` exist
  - `panel_api.discover_root(exe_dir: Path | None = None, default: Path | None = None) -> Path | None`
  - `panel_api.Panel(root: Path)` with `.root`

- [ ] **Step 1: Write the failing test**

Create `apps/windows-panel/tests/test_panel_api.py`:

```python
import os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # /home/box/jarvis or C:\Users\rajk1\jarvis
sys.path.insert(0, str(ROOT / "apps" / "windows-panel"))
sys.path.insert(0, str(ROOT / "scripts" / "win"))

import panel_api


class TestRoot(unittest.TestCase):
    def test_is_valid_root_requires_state_and_policy(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            self.assertFalse(panel_api.is_valid_root(p))
            (p / "STATE.md").write_text("#", encoding="utf-8")
            self.assertFalse(panel_api.is_valid_root(p))
            (p / "POLICY.yaml").write_text("status: approved\n", encoding="utf-8")
            self.assertTrue(panel_api.is_valid_root(p))

    def test_discover_root_prefers_exe_dir_when_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "STATE.md").write_text("#", encoding="utf-8")
            (p / "POLICY.yaml").write_text("status: approved\n", encoding="utf-8")
            found = panel_api.discover_root(exe_dir=p, default=Path("/nonexistent"))
            self.assertEqual(found, p.resolve())

    def test_jarvis_home_env_override(self):
        import lib_jarvis
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            old = os.environ.get("JARVIS_HOME")
            os.environ["JARVIS_HOME"] = str(p)
            try:
                self.assertEqual(lib_jarvis.jarvis_home(), p.resolve())
            finally:
                if old is None:
                    os.environ.pop("JARVIS_HOME", None)
                else:
                    os.environ["JARVIS_HOME"] = old


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/box/jarvis && python3 apps/windows-panel/tests/test_panel_api.py -v`  
Expected: FAIL (module `panel_api` missing and/or `JARVIS_HOME` ignored)

- [ ] **Step 3: Write minimal implementation**

In `scripts/win/lib_jarvis.py`, replace `jarvis_home` with:

```python
def jarvis_home() -> Path:
    env = os.environ.get("JARVIS_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(r"C:\Users\rajk1\jarvis")
```

Add `import os` at top of `lib_jarvis.py` if missing.

Create `apps/windows-panel/panel_api.py`:

```python
from __future__ import annotations
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\Users\rajk1\jarvis")


def is_valid_root(path: Path) -> bool:
    p = Path(path)
    return (p / "STATE.md").is_file() and (p / "POLICY.yaml").is_file()


def discover_root(exe_dir: Path | None = None, default: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if exe_dir is not None:
        candidates.append(Path(exe_dir))
        # exe living in apps/ → parent may be jarvis root
        candidates.append(Path(exe_dir).parent)
    candidates.append(Path(default) if default is not None else DEFAULT_ROOT)
    for c in candidates:
        try:
            r = c.resolve()
        except Exception:
            continue
        if is_valid_root(r):
            return r
    return None


class Panel:
    def __init__(self, root: Path):
        root = Path(root).resolve()
        if not is_valid_root(root):
            raise ValueError(f"invalid JARVIS_ROOT: {root}")
        self.root = root
```

Create `apps/windows-panel/requirements.txt`:

```
customtkinter>=5.2.0
pyyaml>=6.0
pyinstaller>=6.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/box/jarvis && python3 apps/windows-panel/tests/test_panel_api.py -v`  
Expected: PASS for the three tests above

- [ ] **Step 5: Commit**

```bash
git add scripts/win/lib_jarvis.py apps/windows-panel/panel_api.py apps/windows-panel/tests/test_panel_api.py apps/windows-panel/requirements.txt
git commit -m "feat(panel): JARVIS_HOME override and root discovery"
```

---
