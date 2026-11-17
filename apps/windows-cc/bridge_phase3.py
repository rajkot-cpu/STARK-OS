# apps/windows-cc/bridge_phase3.py
"""Phase 3 bridge calls (mixed into BridgeApi): local AI, keys, local API, memory DB,
task queue + chain orchestrator, trading (real indicators, paper ledger, live gate)."""
from __future__ import annotations

import threading

HALTED = {"ok": False, "halted": True, "error": "Emergency STOP is active. Type RESUME (or press Resume) to continue."}


def _err(e: Exception) -> dict:
    return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


class Phase3Mixin:
    # ---- lazy singletons (underscore attrs: never exposed to JS) ----
    def _p3(self):
        st = self.__dict__.get("_p3_state")
        if st is None:
            import memory_db
            import orchestrator
            import task_queue

            q = task_queue.TaskQueue(self.root)
            rec = q.recover()
            mem = memory_db.MemoryDB(self.root)
            orch = orchestrator.Orchestrator(self.root, q, mem, is_halted=self._stopped, on_event=self._on_chain_event)
            st = {"queue": q, "memory": mem, "orch": orch, "recovered": rec, "api": None, "lock": threading.Lock()}
            self.__dict__["_p3_state"] = st
        return st

    def _on_chain_event(self, tid: str, kind: str, text: str) -> None:
        try:
            import cc_settings

            cc_settings.audit(self.root, f"chain-{tid}", f"chain_{kind}", text[:200])
            if kind == "done":
                self.speak("Research chain finished. The report is in workspace reports.")
        except Exception:
            pass

    def _p3_halt_hooks(self, ctl) -> None:
        ctl.on_stop("chains", lambda: self._p3()["orch"].stop_all("Emergency STOP"))
        ctl.on_stop("local_api", lambda: "requests blocked (423) until RESUME")

    # ---- local API ----
    def start_local_api(self) -> dict:
        try:
            import cc_settings
            import jarvis_api

            s = cc_settings.load(self.root)
            if not s.get("api_enabled", True):
                return {"ok": True, "data": {"api": "disabled"}}
            st = self._p3()
            if st["api"] is None:
                st["api"] = jarvis_api.LocalApi(self, port=s.get("api_port", 8765),
                                                audit=lambda t, a, r: cc_settings.audit(self.root, t, a, r))
            r = st["api"].start()
            if not r.get("ok"):
                from bridge_api import log_error

                log_error(self.root, "local_api", r.get("error", ""), "warn")
            return r
        except Exception as e:
            return _err(e)

    def stop_local_api(self) -> None:
        st = self.__dict__.get("_p3_state")
        if st and st.get("api"):
            st["api"].stop()

    def api_info(self) -> dict:
        try:
            import cc_settings
            import jarvis_api
            import secrets_store

            st = self._p3()
            s = cc_settings.load(self.root)
            info = st["api"].info() if st["api"] else {
                "running": False, "port": s.get("api_port", 8765), "error": "",
                "base": f"http://127.0.0.1:{s.get('api_port', 8765)}/v1", "requests": 0,
                "token_location": "Windows Credential Manager -> JARVIS/JARVIS_API_TOKEN",
                "endpoints": [{"method": m, "path": p, "desc": d} for m, p, d in jarvis_api.ENDPOINTS]}
            info["enabled"] = bool(s.get("api_enabled", True))
            info["token_set"] = bool(secrets_store.available() and secrets_store.read(jarvis_api.TOKEN_NAME))
            return {"ok": True, "data": info}
        except Exception as e:
            return _err(e)

    def api_token_copy(self) -> dict:
        """Copy the API token to the clipboard (operator click). The token is never returned to JS."""
        try:
            import subprocess

            import jarvis_api

            tok = jarvis_api.get_or_create_token()
            if not tok:
                return {"ok": False, "error": "no token (Credential Manager unavailable)"}
            subprocess.run(["clip"], input=tok.encode("utf-16-le"), check=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            import cc_settings

            cc_settings.audit(self.root, "local-api", "api_token_copied", "token copied to clipboard (value not logged)")
            return {"ok": True, "data": {"copied": True}}
        except Exception as e:
            return _err(e)

    def api_token_rotate(self, confirmed: bool = False) -> dict:
        if confirmed is not True:
            return {"ok": False, "error": "confirmation required"}
        try:
            import cc_settings
            import jarvis_api

            ok = jarvis_api.rotate_token()
            cc_settings.audit(self.root, "local-api", "api_token_rotated", "new token in Credential Manager" if ok else "failed")
            return {"ok": True, "data": {"rotated": True}} if ok else {"ok": False, "error": "could not rotate token"}
        except Exception as e:
            return _err(e)

    def api_status(self) -> dict:
        """Compact status for GET /v1/status (also works during STOP)."""
        try:
            import cc_settings
            import local_llm
            from bridge_api import APP_VERSION

            s = cc_settings.load(self.root)
            hub = self.__dict__.get("_hub")
            active = sum(1 for a in hub.list() if a["state"] == "active") if hub else 0
            st = self._p3()
            return {"ok": True, "data": {
                "app": "JARVIS", "version": APP_VERSION, "halted": self._stopped(),
                "ai_mode": s.get("ai_mode"), "local_ai": local_llm.status(s.get("local_model", "")),
                "agents_active": active, "chains_running": st["orch"].running(),
                "trading": {"mode": s.get("trading_mode"), "live_enabled": bool(s.get("live_trading_enabled"))}}}
        except Exception as e:
            return _err(e)

    # ---- local AI ----
    def local_ai_status(self) -> dict:
        try:
            import cc_settings
            import llm_router
            import local_llm

            s = cc_settings.load(self.root)
            return {"ok": True, "data": {"ollama": local_llm.status(s.get("local_model", "")), "ai_mode": s.get("ai_mode"),
                                         "configured_model": s.get("local_model"), "plan": llm_router.plan(self.root),
                                         "plan_cheap": llm_router.plan(self.root, cheap=True)}}
        except Exception as e:
            return _err(e)

    def local_ai_test(self, prompt: str = "") -> dict:
        if self._stopped():
            return HALTED
        try:
            import cc_settings
            import local_llm

            s = cc_settings.load(self.root)
            r = local_llm.chat([{"role": "user", "content": str(prompt or "In one sentence, who are you?")[:500]}],
                               model=s.get("local_model", ""), system="You are JARVIS, a concise assistant.",
                               max_tokens=80, timeout=180)
            return {"ok": True, "data": r}
        except Exception as e:
            return _err(e)

    def ask(self, text: str = "", local: bool = False) -> dict:
        if self._stopped():
            return HALTED
        text = str(text or "").strip()[:8000]
        if not text:
            return {"ok": False, "error": "empty text"}
        try:
            import llm_router

            r = llm_router.complete(text, "You are JARVIS, a precise assistant for Dr. Chandan Kumar.", self.root,
                                    cheap=bool(local), max_tokens=800)
            if r.get("halted"):
                return HALTED
            if not r["ok"]:
                return {"ok": False, "error": "; ".join(r["errors"])}
            return {"ok": True, "data": {"text": r["text"], "provider": r["provider"]}, "errors": r["errors"]}
        except Exception as e:
            return _err(e)

    # ---- keys ----
    def keys_status(self) -> dict:
        try:
            import keys_manager

            return {"ok": True, "data": keys_manager.status(self.root)}
        except Exception as e:
            return _err(e)

    def key_set(self, name: str = "", value: str = "") -> dict:
        try:
            import keys_manager

            return keys_manager.set_key(self.root, name, value)
        except Exception as e:
            return _err(e)

    def key_test(self, provider: str = "") -> dict:
        """Read-only connection check for a provider key (never places or tests orders)."""
        if self._stopped():
            return HALTED
        try:
            import cc_settings
            import provider_tests

            r = provider_tests.run(str(provider or ""), self.root)
            cc_settings.audit(self.root, "keys", "key_test", f"{provider}: {r.get('status')}")
            return {"ok": True, "data": r}
        except Exception as e:
            return _err(e)

    def key_delete(self, name: str = "", confirmed: bool = False) -> dict:
        try:
            import keys_manager

            return keys_manager.delete_key(self.root, name, confirmed)
        except Exception as e:
            return _err(e)

    # ---- memory DB ----
    def memory_search(self, q: str = "", limit: int = 20) -> dict:
        try:
            m = self._p3()["memory"]
            return {"ok": True, "data": {"q": str(q or ""), "results": m.search(str(q or ""), int(limit or 20)),
                                         "stats": m.stats()}}
        except Exception as e:
            return _err(e)

    def memory_reindex(self) -> dict:
        try:
            return {"ok": True, "data": self._p3()["memory"].reindex_files()}
        except Exception as e:
            return _err(e)

    def memory_note_add(self, title: str = "", text: str = "", source: str = "ui") -> dict:
        if self._stopped():
            return HALTED
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "empty note"}
        try:
            nid = self._p3()["memory"].add("note", str(title or text[:60]), text[:20000], source=str(source)[:20])
            return {"ok": True, "data": {"id": nid}}
        except Exception as e:
            return _err(e)

    # ---- tasks / chain ----
    def tasks_list(self, limit: int = 30) -> dict:
        try:
            st = self._p3()
            return {"ok": True, "data": {"tasks": st["queue"].list(int(limit or 30)), "recovered": st["recovered"]}}
        except Exception as e:
            return _err(e)

    def task_get(self, tid: str = "") -> dict:
        try:
            t = self._p3()["queue"].get(str(tid))
            return {"ok": True, "data": t} if t else {"ok": False, "error": "no such task"}
        except Exception as e:
            return _err(e)

    def chain_start(self, topic: str = "", source: str = "ui") -> dict:
        if self._stopped():
            return HALTED
        try:
            r = self._p3()["orch"].submit(str(topic or ""), source=str(source)[:10])
            if r.get("ok"):
                import cc_settings

                cc_settings.audit(self.root, f"chain-{r['data']['id']}", "chain_start", f"[{source}] {str(topic)[:180]}")
            return r
        except Exception as e:
            return _err(e)

    def task_retry(self, tid: str = "") -> dict:
        if self._stopped():
            return HALTED
        try:
            return self._p3()["orch"].run(str(tid))
        except Exception as e:
            return _err(e)

    def task_cancel(self, tid: str = "") -> dict:
        try:
            return {"ok": self._p3()["orch"].cancel(str(tid))}
        except Exception as e:
            return _err(e)

    # ---- trading ----
    def trading_snapshot(self, symbol: str = "NIFTY", tf: str = "1d") -> dict:
        try:
            import trading_engine

            return trading_engine.snapshot(str(symbol or "NIFTY"), str(tf or "1d"))
        except Exception as e:
            return _err(e)

    def trading_news(self, symbol: str = "NIFTY") -> dict:
        if self._stopped():
            return HALTED
        try:
            import trading_engine

            return trading_engine.headlines_sentiment(str(symbol or "NIFTY"), self.root)
        except Exception as e:
            return _err(e)

    def _ledger(self):
        st = self._p3()
        if "ledger" not in st:
            import paper_ledger

            st["ledger"] = paper_ledger.PaperLedger(self.root)
        return st["ledger"]

    def paper_summary(self) -> dict:
        try:
            import market_data

            led = self._ledger()
            marks = {}
            for sym in led.symbols():
                r = market_data.fetch(sym, "1d")
                if r.get("ok"):
                    marks[sym] = r["last"]
            return {"ok": True, "data": led.summary(marks)}
        except Exception as e:
            return _err(e)

    def paper_order(self, symbol: str = "NIFTY", side: str = "BUY", qty: float = 1, client_order_id: str = "",
                    origin: str = "manual") -> dict:
        """Operator pressed Buy/Sell (paper). Fills at the last delayed price; never touches a broker."""
        if self._stopped():
            return HALTED
        try:
            import cc_settings
            import market_data

            md = market_data.fetch(str(symbol).upper(), "1d")
            if not md.get("ok"):
                return {"ok": False, "error": "no price: " + md.get("error", "market data unavailable")}
            r = self._ledger().place(str(symbol).upper(), side, qty, md["last"], price_time=md["market_time"],
                                     source=md["source"], origin=str(origin)[:20], client_order_id=str(client_order_id or ""))
            if r.get("ok") and not r.get("duplicate"):
                d = r["data"]
                cc_settings.audit(self.root, "paper-trading", "paper_order",
                                  f"{d['id']} {d['side']} {d['qty']:g} {d['symbol']} @ {d['price']:.2f} ({origin}; PAPER, no broker)")
                try:
                    self._p3()["memory"].add("trade_journal", f"PAPER {d['side']} {d['symbol']}",
                                             f"{d['side']} {d['qty']:g} {d['symbol']} at {d['price']:.2f} (delayed price, "
                                             f"{origin}). Order {d['id']}.", source="paper", tags="paper,trading")
                except Exception:
                    pass
            return r
        except Exception as e:
            return _err(e)

    def paper_reset(self, confirmed: bool = False) -> dict:
        if confirmed is not True:
            return {"ok": False, "error": "confirmation required"}
        try:
            import cc_settings

            self._ledger().reset()
            cc_settings.audit(self.root, "paper-trading", "paper_reset", "paper ledger cleared")
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def live_status(self) -> dict:
        try:
            import broker_live
            import cc_settings
            import keys_manager

            return {"ok": True, "data": broker_live.status(cc_settings.load(self.root),
                                                           key_present=lambda n: bool(keys_manager.where(n, self.root)))}
        except Exception as e:
            return _err(e)

    def live_order(self, symbol: str = "", side: str = "", qty: float = 0, typed: str = "", broker: str = "sahi") -> dict:
        """Live order request from the Jarvis window. Fail-closed (see broker_live gates)."""
        try:
            import broker_live
            import cc_settings
            import keys_manager

            r = broker_live.place_live_order({"symbol": symbol, "side": side, "qty": qty},
                                             settings=cc_settings.load(self.root), halted=self._stopped(), origin="ui",
                                             typed=str(typed or ""), broker=str(broker or "sahi"),
                                             key_present=lambda n: bool(keys_manager.where(n, self.root)))
            cc_settings.audit(self.root, "live-trading", "live_order_refused" if not r.get("ok") else "live_order",
                              f"gate {r.get('gate')}: {r.get('error', '')[:160]}")
            return r
        except Exception as e:
            return _err(e)
