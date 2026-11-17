# apps/windows-cc/orchestrator.py
"""Chained agent work (Phase 3): Research -> Analyst -> Writer, backed by the persistent task queue.

Every step is a real model call (hybrid router: cloud first, local Ollama fallback). Research uses
the same read-only web search the agents use, plus Jarvis memory. The Writer's report is saved to
<root>/workspace/reports/ and indexed into the memory DB. STOP cancels the chain between and during
steps (the HTTP call in flight is abandoned); nothing restarts after a STOP or a restart.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
CHAIN = ("research", "analyst", "writer")
LABEL = {"research": "Research", "analyst": "Analyst", "writer": "Writer"}

SYS_RESEARCH = ("You are the Research agent of JARVIS. Using ONLY the numbered sources and memory notes given, "
                "write concise research notes (bullets) on the topic. Cite sources as [n]. If the sources do not "
                "cover something, say so. Never invent facts, numbers or URLs.")
SYS_ANALYST = ("You are the Analyst agent of JARVIS. From the research notes, produce: Key findings (ranked), "
               "Implications, Risks/unknowns, and a confidence level (low/medium/high) with one-line reasons. "
               "Keep [n] citations. Do not add facts that are not in the notes.")
SYS_WRITER = ("You are the Writer agent of JARVIS. Write a clear markdown report for Dr. Chandan Kumar with: "
              "a title line starting with '# ', an Executive summary (3-5 bullets), Findings, Analysis, and Next steps. "
              "Keep [n] citations. Do not write a Sources section (it is appended automatically). Do not invent facts.")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s[:48].rstrip("-") or "report")


class Orchestrator:
    def __init__(self, root: Path | str, queue, memory, is_halted=lambda: False, complete=None, search=None,
                 on_event=None):
        self.root = Path(root)
        self.queue = queue
        self.memory = memory
        self.is_halted = is_halted
        self._complete = complete
        self._search = search
        self.on_event = on_event
        self._cancel: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    # ---- deps ----
    def complete(self, prompt: str, system: str) -> dict:
        if self._complete:
            return self._complete(prompt, system)
        import llm_router

        return llm_router.complete(prompt, system, self.root, max_tokens=1200, timeout=90)

    def search(self, query: str) -> dict:
        if self._search:
            return self._search(query)
        from agent_tools import AgentTools

        return AgentTools(self.root, actor="agent-research").web_search(query, max_results=6)

    # ---- control ----
    def submit(self, topic: str, source: str = "ui") -> dict:
        topic = " ".join(str(topic or "").split())[:300]
        if not topic:
            return {"ok": False, "error": "topic is empty"}
        if self.is_halted():
            return {"ok": False, "halted": True, "error": "Emergency STOP is active. Type RESUME first."}
        t = self.queue.add("chain", topic, {"topic": topic, "chain": list(CHAIN)}, source=source)
        return self.run(t["id"])

    def run(self, tid: str) -> dict:
        if self.is_halted():
            return {"ok": False, "halted": True, "error": "Emergency STOP is active. Type RESUME first."}
        if not self.queue.claim(tid):
            return {"ok": False, "error": "task is not runnable (already running, done or cancelled)"}
        ev = threading.Event()
        th = threading.Thread(target=self._run, args=(tid, ev), daemon=True, name=f"chain-{tid}")
        with self._lock:
            self._cancel[tid] = ev
            self._threads[tid] = th
        th.start()
        return {"ok": True, "data": self.queue.get(tid)}

    def cancel(self, tid: str) -> bool:
        with self._lock:
            ev = self._cancel.get(tid)
        if ev:
            ev.set()
        return self.queue.cancel(tid)

    def stop_all(self, reason: str = "Emergency STOP") -> int:
        with self._lock:
            for ev in self._cancel.values():
                ev.set()
        return self.queue.cancel_running(reason)

    def wait(self, tid: str, timeout: float = 600.0) -> dict | None:
        th = self._threads.get(tid)
        if th:
            th.join(timeout)
        return self.queue.get(tid)

    def running(self) -> int:
        return sum(1 for t in self._threads.values() if t.is_alive())

    # ---- worker ----
    def _emit(self, tid: str, kind: str, text: str) -> None:
        if self.on_event:
            try:
                self.on_event(tid, kind, text)
            except Exception:
                pass

    def _check(self, ev: threading.Event) -> None:
        if ev.is_set() or self.is_halted():
            raise _Cancelled()

    def _run(self, tid: str, ev: threading.Event) -> None:
        task = self.queue.get(tid) or {}
        topic = str((task.get("payload") or {}).get("topic") or task.get("title") or "")
        steps: list[dict] = []
        try:
            # 1. Research
            self._check(ev)
            self.queue.update(tid, step=1, steps=steps)
            t0 = time.time()
            sr = self.search(topic)
            sources = (sr.get("data") or {}).get("results") if sr.get("ok") else None
            if sources is None and sr.get("ok"):
                sources = sr.get("data") if isinstance(sr.get("data"), list) else []
            sources = [s for s in (sources or []) if isinstance(s, dict) and s.get("url")][:6]
            summary = str(((sr.get("data") or {}) if sr.get("ok") else {}).get("summary") or "")[:1500]
            mem = []
            try:
                mem = self.memory.search(topic, limit=4)
            except Exception:
                pass
            self._check(ev)
            src_txt = "\n".join(f"[{i+1}] {s.get('title','')}: {s.get('snippet','')} ({s['url']})"
                                for i, s in enumerate(sources)) or "(web search returned nothing)"
            if summary:
                src_txt += f"\n\nSearch summary (Google grounding): {summary}"
            mem_txt = "\n".join(f"- {m['title']}: {m['snippet']}" for m in mem) or "(no related memory)"
            r1 = self.complete(f"Topic: {topic}\n\nSources:\n{src_txt}\n\nMemory notes:\n{mem_txt}", SYS_RESEARCH)
            self._step_done(tid, steps, "research", r1, t0, extra={"sources": len(sources),
                                                                   "search_error": "" if sr.get("ok") else str(sr.get("error", ""))[:120]})
            # 2. Analyst
            self._check(ev)
            t0 = time.time()
            r2 = self.complete(f"Topic: {topic}\n\nResearch notes:\n{r1['text']}", SYS_ANALYST)
            self._step_done(tid, steps, "analyst", r2, t0)
            # 3. Writer
            self._check(ev)
            t0 = time.time()
            r3 = self.complete(f"Topic: {topic}\n\nResearch notes:\n{r1['text']}\n\nAnalysis:\n{r2['text']}", SYS_WRITER)
            self._step_done(tid, steps, "writer", r3, t0)
            self._check(ev)
            body = r3["text"].strip()
            if not body.startswith("# "):
                body = f"# {topic}\n\n{body}"
            when = datetime.now(_IST)
            prov = ", ".join(f"{LABEL[s['agent']]}: {s['provider']}" for s in steps)
            body += "\n\n## Sources\n" + ("\n".join(f"{i+1}. [{s.get('title') or s['url']}]({s['url']})"
                                                    for i, s in enumerate(sources)) or "_No web sources were returned._")
            body += f"\n\n---\n_Generated by JARVIS chain Research → Analyst → Writer on {when:%d %b %Y %H:%M} IST ({prov})._\n"
            out_dir = self.root / "workspace" / "reports"
            out_dir.mkdir(parents=True, exist_ok=True)
            f = out_dir / f"{when:%Y%m%d-%H%M%S}-{_slug(topic)}.md"
            f.write_text(body, encoding="utf-8")
            rel = str(f.relative_to(self.root)).replace("\\", "/")
            try:
                self.memory.add("report", topic, body, source=rel, tags="chain,report")
            except Exception:
                pass
            self.queue.update(tid, state="done", step=4, steps=steps, result=rel)
            self._emit(tid, "done", f"Chain finished: {rel}")
        except _Cancelled:
            self.queue.update(tid, state="cancelled", steps=steps,
                              error="Emergency STOP" if self.is_halted() else "cancelled by operator")
            self._emit(tid, "cancelled", topic)
        except Exception as e:
            self.queue.update(tid, state="error", steps=steps, error=str(e)[:300])
            self._emit(tid, "error", str(e)[:200])
        finally:
            with self._lock:
                self._cancel.pop(tid, None)

    def _step_done(self, tid, steps, agent, r, t0, extra=None):
        if r.get("halted"):
            raise _Cancelled()
        if not r.get("ok"):
            raise RuntimeError(f"{LABEL[agent]} step failed: " + "; ".join(r.get("errors") or [])[:240])
        row = {"agent": agent, "provider": r.get("provider", ""), "seconds": round(time.time() - t0, 1),
               "chars": len(r.get("text") or "")}
        row.update(extra or {})
        steps.append(row)
        self.queue.update(tid, step=len(steps) + 1, steps=steps)


class _Cancelled(Exception):
    pass
