# apps/windows-cc/bridge_api.py
from __future__ import annotations

from pathlib import Path
import sys

_PANEL = Path(__file__).resolve().parents[1] / "windows-panel"
_WIN = Path(__file__).resolve().parents[2] / "scripts" / "win"
for p in (_PANEL, _WIN, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import panel_api  # noqa: E402


def _system_status(status: dict) -> str:
    if not status.get("policy_ok"):
        return "POLICY NOT APPROVED"
    if status.get("quiet_hours"):
        return "QUIET HOURS"
    return "SYSTEMS NOMINAL"


class BridgeApi:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.panel = panel_api.Panel(self.root)
        self._hub = None

    def status(self) -> dict:
        try:
            s = self.panel.status_strip()
            muted = False
            try:
                import voice

                muted = bool(voice.is_muted())
            except Exception:
                muted = False
            return {
                "ok": True,
                "data": {
                    "system_status": _system_status(s),
                    "quiet_hours": bool(s.get("quiet_hours", False)),
                    "muted": muted,
                    "policy_ok": bool(s.get("policy_ok")),
                    "today": s.get("today"),
                    "root": s.get("root"),
                },
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def metrics(self) -> dict:
        try:
            from metrics import snapshot

            return {"ok": True, "data": snapshot()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


    def readiness(self) -> dict:
        """Weighted Jarvis readiness score. Never includes secret values."""
        try:
            from readiness import compute_readiness

            return {"ok": True, "data": compute_readiness(self.root)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def feed(self, limit: int = 50) -> dict:
        try:
            from feed import tail

            return {"ok": True, "data": {"items": tail(self.root, n=int(limit))}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def memory(self) -> dict:
        try:
            from memory_index import build

            return {"ok": True, "data": build(self.root)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def llms(self) -> dict:
        try:
            from llm_providers import probe_all

            return {"ok": True, "data": {"providers": probe_all(root=self.root)}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _agents_hub(self):
        if self._hub is None:
            from agents.worker import AgentHub

            self._hub = AgentHub(root=self.root)
        return self._hub

    def agents(self) -> dict:
        try:
            return {"ok": True, "data": {"agents": self._agents_hub().list()}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def agent_start(self, role_id: str, goal: str = "") -> dict:
        try:
            return self._agents_hub().start(str(role_id), goal=str(goal or ""))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def agent_stop(self, role_id: str) -> dict:
        try:
            return self._agents_hub().stop(str(role_id))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def shell_confirm(self, command: str, role_id: str = "") -> dict:
        """Run an R3-confirmed (non-allowlisted) shell command."""
        try:
            from agent_tools import AgentTools

            cmd = str(command or "").strip()
            if not cmd:
                return {"ok": False, "error": "empty command"}
            from shell_gate import normalize

            rid = str(role_id or "").strip()
            if not rid:
                return {"ok": False, "error": "role_id required"}
            hub = self._agents_hub()
            detail = str(getattr(hub, "_detail", {}).get(rid) or "")
            if not detail.startswith("needs_r3:"):
                return {"ok": False, "error": "no pending R3 command for role"}
            pending = detail[len("needs_r3:"):].strip()
            if normalize(pending) != normalize(cmd):
                return {"ok": False, "error": "command does not match pending R3 request"}
            try:
                return AgentTools(self.root).shell(cmd, confirmed=True)
            finally:
                # Clear after any authorized attempt so the UI never sticks.
                hub.clear_r3(rid)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def listen(self, timeout: float = 5.0) -> dict:
        try:
            from stt import listen_once

            return listen_once(timeout=float(timeout))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def speak(self, text: str = "") -> dict:
        try:
            import voice

            voice.speak(str(text or ""))
            return {"ok": True, "data": {"spoken": True}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def mute(self, on: bool = True) -> dict:
        try:
            import voice

            voice.set_muted(bool(on))
            return {"ok": True, "data": {"muted": bool(voice.is_muted())}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def session_start(self) -> dict:
        try:
            code, out, err = self.panel.session_start()
            if code == 0:
                return {"ok": True, "data": {"out": out}}
            return {"ok": False, "error": (err or out or f"exit {code}").strip()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def dry_run_workday(self) -> dict:
        try:
            code, out, err = self.panel.workday(dry=True)
            if code == 0:
                return {"ok": True, "data": {"out": out, "dry": True}}
            return {"ok": False, "error": (err or out or f"exit {code}").strip()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def start_workday(self, confirmed: bool = False) -> dict:
        if not confirmed:
            return {"ok": False, "error": "R3 confirmation required"}
        try:
            code, out, err = self.panel.workday(dry=False)
            if code == 0:
                return {"ok": True, "data": {"out": out, "dry": False}}
            return {"ok": False, "error": (err or out or f"exit {code}").strip()}
        except Exception as e:
            return {"ok": False, "error": str(e)}


    def chat(self, text: str = "") -> dict:
        try:
            from chat import reply

            return reply(str(text or ""), root=self.root)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def voice_turn(self, timeout: float = 5.0) -> dict:
        """Listen once, local ack, Gemini reply; returns heard + reply (speak from JS)."""
        try:
            from stt import listen_once
            import voice

            heard = listen_once(timeout=float(timeout))
            if not heard.get("ok"):
                return heard
            text = heard.get("text") or ""
            try:
                voice.speak("Yes sir.", wait=False)
            except Exception:
                pass
            from chat import reply

            ans = reply(text, root=self.root)
            if not ans.get("ok"):
                return {"ok": False, "error": ans.get("error") or "chat failed", "text": text}
            return {
                "ok": True,
                "text": text,
                "reply": ans["data"]["reply"],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def brief(self) -> dict:
        try:
            return {"ok": True, "data": {"text": self.panel.today_brief() or ""}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def skills(self) -> dict:
        try:
            rows = []
            for s in self.panel.list_skills():
                rows.append(
                    {
                        "name": s.get("name"),
                        "summary": s.get("summary") or "",
                        "risk": s.get("risk") or "read",
                    }
                )
            return {"ok": True, "data": {"skills": rows}}
        except Exception as e:
            return {"ok": False, "error": str(e)}
