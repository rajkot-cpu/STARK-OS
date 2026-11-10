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
import threading  # noqa: E402


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
        self._wake = None
        self._wake_busy = threading.Lock()
        self._wake_info = {"state": "idle", "heard": "", "reply": "", "error": "", "engine": ""}

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

            self._hub = AgentHub(root=self.root, on_event=self._on_agent_event)
        return self._hub

    def _on_agent_event(self, role_id: str, kind: str, row: dict) -> None:
        """Agent finished / failed / needs approval: Live Feed line + short spoken report."""
        try:
            import cc_settings

            name = row.get("name") or role_id
            files = row.get("files") or []
            prov = row.get("provider") or ""
            if kind == "done":
                summary = str(row.get("last_reply") or "").strip()
                extra = f"; files: {', '.join(files[:8])}" if files else ""
                cc_settings.audit(self.root, f"agent-{role_id}", "agent_done",
                                  f"{summary[:200]}{extra} [{prov}]")
                first = summary.split("\n", 1)[0].split(". ", 1)[0][:160]
                say = f"{name} finished. " + (f"Created {len(files)} file{'s' if len(files) != 1 else ''}. " if files else "") + first
            elif kind == "needs_approval":
                label = (row.get("pending") or {}).get("label") or str(row.get("detail") or "")[:120]
                cc_settings.audit(self.root, f"agent-{role_id}", "agent_needs_approval", label)
                say = f"{name} needs your approval on the Agents page."
            else:
                cc_settings.audit(self.root, f"agent-{role_id}", "agent_error", str(row.get("detail") or "")[:200])
                say = f"{name} hit a problem: {str(row.get('detail') or '')[:120]}"
            self.speak(say)
        except Exception:
            pass

    def command(self, text: str = "") -> dict:
        """Typed or spoken command: start the right agent now, else answer via chat."""
        try:
            return self._route(str(text or ""), speak=False)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _route(self, text: str, speak: bool = False) -> dict:
        from voice_intents import announce, match

        m = match(text)
        intent = m["intent"]
        if intent == "agent":
            from agents.registry import ROLES

            hub = self._agents_hub()
            name = next((r["name"] for r in ROLES if r["id"] == m["role"]), m["role"])
            r = hub.start(m["role"], goal=m["goal"])
            if not r.get("ok"):
                say = f"{name} is still busy with its last job. Stop it first or wait."
                return {"ok": True, "data": {"routed": "agent", "role": m["role"], "started": False,
                                             "reply": say, "error": r.get("error")}}
            say = announce(name, m["verb"], m["goal"])
            import cc_settings

            cc_settings.audit(self.root, f"agent-{m['role']}", "agent_start_by_command", m["goal"][:200])
            if speak:
                self.speak(say)
            return {"ok": True, "data": {"routed": "agent", "role": m["role"], "goal": m["goal"],
                                         "started": True, "reply": say}}
        if intent == "stop_agent":
            self._agents_hub().stop(m["role"])
            say = f"Stopped the {m['role']} agent."
            return {"ok": True, "data": {"routed": "stop_agent", "role": m["role"], "reply": say}}
        if intent in ("start_trading", "stop_trading"):
            # Reserved for the voice-trading release; nothing is armed or traded here.
            say = "Voice trading isn't switched on in this version yet. No trading was started."
            return {"ok": True, "data": {"routed": intent, "reply": say}}
        from chat import reply

        ans = reply(text, root=self.root)
        if not ans.get("ok"):
            return {"ok": False, "error": ans.get("error") or "chat failed"}
        return {"ok": True, "data": {"routed": "chat", "reply": ans["data"]["reply"],
                                     "provider": ans["data"].get("provider", "")}}

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
            cwd = hub.pending_shell_cwd(rid) if hasattr(hub, "pending_shell_cwd") else ""
            result = {"ok": False, "error": "shell failed"}
            try:
                result = AgentTools(self.root, actor=f"agent-{rid}").shell(cmd, confirmed=True, cwd=cwd)
                return result
            finally:
                # Clear after any authorized attempt so the UI never sticks.
                hub.clear_r3(rid)
                if hasattr(hub, "resume"):
                    hub.resume(rid, result)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def listen(self, timeout: float = 5.0) -> dict:
        try:
            from stt import listen_once

            return listen_once(timeout=float(timeout))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _voice_id(self) -> str:
        try:
            from cc_settings import load

            return load(self.root)["voice"]
        except Exception:
            return "en-IN-PrabhatNeural"

    def speak(self, text: str = "") -> dict:
        try:
            import tts

            tts.speak(str(text or ""), self._voice_id())
            return {"ok": True, "data": {"spoken": True}}
        except Exception as e:
            try:
                import voice

                voice.speak(str(text or ""))
                return {"ok": True, "data": {"spoken": True, "engine": "voice"}}
            except Exception:
                return {"ok": False, "error": str(e)}

    def stop_speaking(self) -> dict:
        """Stop control / barge-in: interrupt whatever Jarvis is saying."""
        try:
            import tts

            return {"ok": True, "data": {"was_speaking": bool(tts.stop())}}
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

            heard = listen_once(timeout=float(timeout), root=self.root)
            if not heard.get("ok"):
                return heard
            text = heard.get("text") or ""
            try:
                import tts

                tts.speak("Yes sir.", self._voice_id())
            except Exception:
                try:
                    voice.speak("Yes sir.", wait=False)
                except Exception:
                    pass
            ans = self._route(text, speak=False)
            if not ans.get("ok"):
                return {"ok": False, "error": ans.get("error") or "chat failed", "text": text}
            return {
                "ok": True,
                "text": text,
                "reply": ans["data"]["reply"],
                "routed": ans["data"].get("routed", "chat"),
                "role": ans["data"].get("role", ""),
                "engine": heard.get("engine", ""),
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

    # ---- Settings / opt-in features (wake word, STT, voice, MCP, screen) ----

    def _wake_view(self) -> dict:
        try:
            from wakeword import available

            ok, why = available()
        except Exception as e:
            ok, why = False, type(e).__name__
        w = self._wake
        return {
            "available": ok,
            "reason": why,
            "running": bool(w and w.running),
            "listener_state": (w.state if w else "off"),
            "listener_error": (w.error if w else ""),
            "wakes": (w.wakes if w else 0),
            "barge_ins": (w.barge_ins if w else 0),
            **self._wake_info,
        }

    def settings_get(self) -> dict:
        try:
            import cc_settings
            import mcp_client
            import stt
            import tts

            s = cc_settings.load(self.root)
            try:
                from screen import available as scr_avail

                scr_ok, scr_why = scr_avail()
            except Exception as e:
                scr_ok, scr_why = False, type(e).__name__
            return {"ok": True, "data": {
                "settings": s,
                "voices": [dict(v) for v in cc_settings.VOICES],
                "stt_engines": [dict(e) for e in cc_settings.STT_ENGINES],
                "whisper": stt.whisper_status(self.root, s["whisper_model"]),
                "wake": self._wake_view(),
                "edge_available": tts.edge_available(),
                "speaking": tts.is_speaking(),
                "mcp": mcp_client.public_view(self.root),
                "screen": {"available": scr_ok, "reason": scr_why},
                "settings_path": str(cc_settings.settings_path(self.root)),
            }}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def settings_set(self, updates: dict | None = None, confirmed: bool = False) -> dict:
        """Change settings. Turning the wake word ON is R3 (UI confirm card)."""
        try:
            import cc_settings

            updates = dict(updates or {})
            cur = cc_settings.load(self.root)
            want_wake = updates.pop("wake_word", None)
            if want_wake is True and not cur["wake_word"]:
                if confirmed is not True:
                    return {"ok": False, "error": "R3 confirmation required to keep the mic listening"}
                r = self._wake_start()
                if not r.get("ok"):
                    return r
                cc_settings.save(self.root, {"wake_word": True})
                cc_settings.audit(self.root, "cc-settings", "wake_word_on",
                                  "Always listen for Hey Jarvis enabled (R3 confirmed)",
                                  "Settings > untick Always listen for Hey Jarvis")
            elif want_wake is False and cur["wake_word"]:
                self._wake_stop()
                cc_settings.save(self.root, {"wake_word": False})
                cc_settings.audit(self.root, "cc-settings", "wake_word_off",
                                  "Always listen for Hey Jarvis disabled", "re-enable in Settings")
            if updates:
                before = cc_settings.load(self.root)
                after = cc_settings.save(self.root, updates)
                changed = {k: after[k] for k in updates if k in after and before.get(k) != after[k]}
                if changed:
                    cc_settings.audit(self.root, "cc-settings", "settings_change",
                                      ", ".join(f"{k}={v}" for k, v in changed.items()))
            return self.settings_get()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _wake_start(self) -> dict:
        from wakeword import WakeListener, available

        ok, why = available()
        if not ok:
            return {"ok": False, "error": why or "wake word unavailable"}
        if self._wake and self._wake.running:
            return {"ok": True}
        import tts

        self._wake = WakeListener(self._on_wake, is_speaking=tts.is_speaking, stop_speaking=tts.stop)
        self._wake.start()
        return {"ok": True}

    def _wake_stop(self) -> None:
        w, self._wake = self._wake, None
        if w:
            w.stop()
        self._wake_info["state"] = "idle"

    def _on_wake(self) -> None:
        """Hey Jarvis heard: run one voice turn (listen -> chat -> speak)."""
        if not self._wake_busy.acquire(blocking=False):
            return
        try:
            self._wake_info.update(state="listening", error="")
            try:
                import winsound

                winsound.MessageBeep()
            except Exception:
                pass
            from stt import listen_once

            w = self._wake
            if w:
                w.pause()
            try:
                heard = listen_once(timeout=6.0, root=self.root)
            finally:
                if w:
                    w.resume()
            if not heard.get("ok"):
                self._wake_info.update(state="idle", error=heard.get("error") or "not heard")
                return
            text = heard.get("text") or ""
            self._wake_info.update(state="thinking", heard=text, engine=heard.get("engine", ""))
            ans = self._route(text, speak=False)
            if not ans.get("ok"):
                self._wake_info.update(state="idle", error=ans.get("error") or "chat failed")
                return
            out = ans["data"]["reply"]
            self._wake_info.update(state="speaking", reply=out)
            import tts

            tts.speak(out, self._voice_id(), wait=True)
            self._wake_info["state"] = "idle"
        except Exception as e:
            self._wake_info.update(state="idle", error=str(e)[:200])
        finally:
            self._wake_busy.release()

    def wake_status(self) -> dict:
        try:
            return {"ok": True, "data": self._wake_view()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def autostart(self) -> dict:
        """At launch: resume the wake word only if the operator enabled it earlier."""
        try:
            import cc_settings

            if cc_settings.load(self.root)["wake_word"]:
                return self._wake_start()
            return {"ok": True, "data": {"wake": "off"}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def shutdown(self) -> None:
        try:
            self._wake_stop()
        except Exception:
            pass
        try:
            import tts

            tts.stop()
        except Exception:
            pass

    def stt_download_model(self) -> dict:
        try:
            import cc_settings
            import stt

            name = cc_settings.load(self.root)["whisper_model"]
            r = stt.download_model(self.root, name, background=True)
            cc_settings.audit(self.root, "cc-settings", "whisper_download",
                              f"{name} -> {stt.models_dir(self.root)}", "delete the models folder")
            return r
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def tts_test(self) -> dict:
        return self.speak("Good day, sir. This is my new voice.")

    def _keys(self) -> tuple[str, str]:
        from llm_providers import _resolve_key, load_secrets

        load_secrets(self.root)
        return (
            _resolve_key("JARVIS_GEMINI_API_KEY", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
            _resolve_key("JARVIS_OPENAI_API_KEY", ("OPENAI_API_KEY",)),
        )

    def screen_read(self, question: str = "", confirmed: bool = False) -> dict:
        """Operator-initiated screen read. R3 every capture (UI confirm card)."""
        if confirmed is not True:
            return {"ok": False, "error": "R3 confirmation required for every screen capture"}
        try:
            import cc_settings
            from screen import read_screen

            g, o = self._keys()
            r = read_screen(str(question or ""), gemini_key=g, openai_key=o)
            cc_settings.audit(self.root, "cc-screen", "screen_capture",
                              f"operator R3; ok={bool(r.get('ok'))}; image kept in memory only",
                              "n/a (nothing stored)")
            return r
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def tool_confirm(self, role_id: str = "", token: str = "") -> dict:
        """Run an agent's pending R3 tool request (MCP call or screen read)."""
        try:
            import cc_settings

            rid = str(role_id or "").strip()
            hub = self._agents_hub()
            pend = hub.take_pending(rid, str(token or ""))
            if not pend:
                return {"ok": False, "error": "no matching pending R3 tool request"}
            if pend["kind"] == "mcp":
                from mcp_client import call_tool

                r = call_tool(self.root, pend["server"], pend["tool"], pend.get("args") or {})
                cc_settings.audit(self.root, f"agent-{rid}", "mcp_call",
                                  f"{pend['server']}.{pend['tool']} ok={bool(r.get('ok'))} (R3 confirmed)",
                                  "depends on the MCP tool")
                text = (r.get("data") or {}).get("text") if r.get("ok") else r.get("error")
                hub.record_result(rid, f"{pend['label']}: {text or ''}")
                hub.resume(rid, r)
                return r
            if pend["kind"] == "screen":
                r = self.screen_read(pend.get("question") or "", confirmed=True)
                desc = (r.get("data") or {}).get("description") if r.get("ok") else r.get("error")
                hub.record_result(rid, f"Screen: {desc or ''}")
                hub.resume(rid, r)
                return r
            if pend["kind"] == "file":
                from agent_tools import AgentTools

                t = AgentTools(self.root, actor=f"agent-{rid}")
                if pend.get("op") == "overwrite":
                    r = t.write_file(pend["path"], pend.get("content") or "", confirmed=True)
                    if r.get("ok"):
                        hub.note_file(rid, pend["path"])
                elif pend.get("op") == "delete":
                    r = t.delete_file(pend["path"], confirmed=True)
                else:
                    r = {"ok": False, "error": "unknown file op"}
                hub.resume(rid, r)
                return r
            return {"ok": False, "error": "unknown pending kind"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def tool_reject(self, role_id: str = "") -> dict:
        try:
            ok = self._agents_hub().reject_pending(str(role_id or ""))
            return {"ok": ok} if ok else {"ok": False, "error": "nothing pending"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
