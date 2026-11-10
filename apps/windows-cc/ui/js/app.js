// apps/windows-cc/ui/js/app.js
import { call, whenReady } from "./bridge.js";
import { mountNavIcons } from "./icons3d.js";
import { mountCore } from "./core3d.js";

let core3d = null;

const $ = (id) => document.getElementById(id);
const banner = (msg) => { $("banner").textContent = msg || ""; };

function setRoute(name) {
  document.querySelectorAll("#nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.route === name);
  });
  document.querySelectorAll(".page").forEach((p) => {
    p.classList.toggle("active", p.id === `page-${name}`);
  });
}

function tickClock() {
  const d = new Date();
  $("clock").textContent = d.toLocaleString("en-IN", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }) + " IST";
}

function renderHealth(status, agents, llms, mem) {
  const connected = (llms || []).filter((p) => p.state === "connected").length;
  const active = (agents || []).filter((a) => a.state === "active").length;
  const muted = !!(status && status.muted);
  const items = [
    ["AI Core", status?.system_status || "—"],
    ["Memory", `${mem?.nodes ?? 0} nodes`],
    ["Voice", muted ? "Muted" : "Online"],
    ["Agents", `${active} running`],
    ["LLMs", `${connected} connected`],
    ["System", status?.quiet_hours ? "Quiet hours" : (status?.policy_ok ? "Optimal" : "Check POLICY")],
  ];
  $("health-list").innerHTML = items.map(([k, v]) => `<li><span>${k}</span><strong>${v}</strong></li>`).join("");
  const pill = $("sys-pill");
  const ok = status?.policy_ok && !status?.quiet_hours;
  pill.textContent = ok ? "OPTIMAL" : (status?.system_status || "CHECK");
  pill.classList.toggle("bad", !ok);
}

function renderReadiness(data) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(data?.score_pct) || 0)));
  const ring = $("ready-ring");
  const num = $("g-ready");
  if (num) num.textContent = String(pct);
  if (ring) {
    ring.style.setProperty("--pct", String(pct));
    ring.classList.remove("ready-high", "ready-mid", "ready-low");
    ring.classList.add(pct >= 80 ? "ready-high" : (pct >= 50 ? "ready-mid" : "ready-low"));
  }
  const list = $("ready-list");
  if (list) {
    list.innerHTML = (data?.checks || []).map((c) => {
      if (c.ok) {
        return `<li class="ready-ok"><span class="tick">✓</span><span>${esc(c.label)}</span></li>`;
      }
      return `<li class="ready-miss"><span class="tick">○</span><span>${esc(c.label)}</span><div class="fix">${esc(c.fix)}</div></li>`;
    }).join("") || `<li class="muted">Readiness checks unavailable.</li>`;
  }
  const extras = $("ready-extras");
  if (extras) {
    const rows = (data?.extras || []);
    extras.innerHTML = rows.length
      ? `<li class="muted">Optional (not scored):</li>` + rows.map((e) =>
          `<li class="${e.ok ? "on" : ""}" title="${esc(e.note)}"><span>${e.ok ? "●" : "○"}</span><span>${esc(e.label)}</span></li>`).join("")
      : "";
  }
  if (core3d) core3d.setHealth(pct / 100);
  const core = $("core-page");
  if (core) {
    const missing = (data?.checks || []).filter((c) => !c.ok);
    const bits = [`<p><strong>Jarvis readiness: ${pct}%</strong></p>`];
    if (missing.length) {
      bits.push("<ul>" + missing.map((c) => `<li>${esc(c.label)} — ${esc(c.fix)}</li>`).join("") + "</ul>");
    } else if (data?.checks?.length) {
      bits.push(`<p class="muted">All readiness checks passed.</p>`);
    }
    bits.push($("health-list") ? $("health-list").innerHTML : "");
    core.innerHTML = bits.join("");
  }
}

const pendingShell = {};

function esc(v) {
  return String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderAgents(agents) {
  const html = (agents || []).map((a) => {
    const steps = (a.steps || []).slice(-5).map((s) => `<li>${esc(s)}</li>`).join("");
    const det = String(a.detail || "");
    const idx = det.indexOf("needs_r3:");
    const pending = det.startsWith("needs_r3:") ? det.slice(idx + "needs_r3:".length) : "";
    pendingShell[a.id] = pending;
    const reply = esc(a.last_reply || a.detail || "");
    return `
    <div class="agent-card">
      <div>
        <div>${esc(a.name)}</div>
        <div class="state-${a.state}">${esc(a.state)}${a.detail ? " · " + esc(a.detail) : ""}</div>
        ${reply ? `<div class="muted agent-reply">${reply}</div>` : ""}
        ${steps ? `<ul class="agent-steps">${steps}</ul>` : ""}
        ${a.pending ? `<div class="tool-r3"><div class="gold">${esc(a.pending.label)} — needs your R3 approval</div>
          ${a.pending.args_preview ? `<code>${esc(a.pending.args_preview)}</code>` : ""}
          ${a.pending.kind === "screen" ? `<div class="muted">Jarvis will capture your screen once and describe it. Nothing is saved.</div>` : ""}
          <button data-tool-confirm="${a.id}" data-token="${esc(a.pending.token)}">Approve once</button>
          <button data-tool-reject="${a.id}">Reject</button></div>` : ""}
        ${pending ? `<div class="shell-r3"><div class="muted">Pending shell (R3):</div><code>${esc(pending)}</code>
          <button data-shell-confirm="${a.id}">Confirm shell</button></div>` : ""}
        <input class="agent-goal" data-goal-for="${a.id}" placeholder="Goal (optional)" />
      </div>
      <button data-agent="${a.id}" data-act="${a.state === "active" ? "stop" : "start"}">
        ${a.state === "active" ? "Stop" : "Start"}
      </button>
    </div>`;
  }).join("");
  $("agents-grid").innerHTML = html;
  $("agents-page").innerHTML = html;
  document.querySelectorAll("[data-shell-confirm]").forEach((btn) => {
    btn.onclick = async () => {
      const cmd = pendingShell[btn.dataset.shellConfirm] || "";
      if (!cmd) return;
      btn.disabled = true;
      const r = await call("shell_confirm", cmd, btn.dataset.shellConfirm);
      banner(r.ok ? "Shell command ran" : (r.error || `shell failed (rc ${r.data?.returncode ?? "?"})`));
      await refresh();
    };
  });
  document.querySelectorAll("[data-tool-confirm]").forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      const r = await call("tool_confirm", btn.dataset.toolConfirm, btn.dataset.token);
      banner(r.ok ? "Approved tool ran — see the agent card" : (r.error || "tool failed"));
      await refresh();
    };
  });
  document.querySelectorAll("[data-tool-reject]").forEach((btn) => {
    btn.onclick = async () => {
      await call("tool_reject", btn.dataset.toolReject);
      banner("Tool request rejected");
      await refresh();
    };
  });
  document.querySelectorAll("[data-agent]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.agent;
      const act = btn.dataset.act;
      const goalEl = document.querySelector(`[data-goal-for="${id}"]`);
      const goal = goalEl ? goalEl.value.trim() : "";
      const r = act === "start"
        ? await call("agent_start", id, goal)
        : await call("agent_stop", id);
      if (!r.ok) banner(r.error || "agent error");
      await refresh();
    };
  });
}

function renderFeed(items, filter) {
  const q = (filter || "").toLowerCase();
  const rows = (items || []).filter((it) => {
    const s = JSON.stringify(it).toLowerCase();
    return !q || s.includes(q);
  }).slice().reverse();
  $("feed-list").innerHTML = rows.map((it) => {
    const t = it.ts_ist || it.ts_utc || it.t || "";
    const msg = it.detail || it.msg || it.action || it.raw || JSON.stringify(it);
    return `<div class="feed-item"><div class="t">${t}</div><div>${msg}</div></div>`;
  }).join("") || `<div class="muted">No audit events yet.</div>`;
  $("conv-page").innerHTML = $("feed-list").innerHTML;
}

function renderMetrics(m) {
  if (!m) return;
  $("g-cpu").textContent = Math.round(m.cpu_pct ?? 0);
  $("g-ram").textContent = Math.round(m.ram_pct ?? 0);
  $("g-disk").textContent = Math.round(m.disk_pct ?? 0);
}

function renderMemory(mem) {
  const nodes = mem?.nodes ?? 0;
  const edges = mem?.edges ?? 0;
  const sources = (mem?.sources || []).join(", ") || "none";
  $("memory-stats").innerHTML = `<div>${nodes} nodes · ${edges} edges</div><div class="muted">Sources: ${sources}</div>`;
  $("memory-page").innerHTML = $("memory-stats").innerHTML;
  $("knowledge-page").innerHTML = `<p class="muted">Indexed sources: ${sources}</p>`;
}

function renderLlms(providers) {
  $("llm-grid").innerHTML = (providers || []).map((p) => `
    <div class="llm ${p.state}">
      <span>${p.name}</span>
      <span>${p.state}</span>
    </div>`).join("") || `<div class="muted">No providers configured.</div>`;
}

function renderTimeline(briefText) {
  const lines = (briefText || "").split("\n").filter(Boolean).slice(0, 12);
  $("timeline").innerHTML = lines.length
    ? lines.map((l) => `<div class="feed-item">${l}</div>`).join("")
    : `<div class="muted">No brief for today yet.</div>`;
  $("calendar-page").innerHTML = $("timeline").innerHTML;
}

function ask(title, body, okLabel) {
  return new Promise((resolve) => {
    $("ask-title").textContent = title;
    $("ask-body").textContent = body;
    $("ask-ok").textContent = okLabel || "Confirm";
    $("ask-modal").classList.remove("hidden");
    const done = (v) => {
      $("ask-modal").classList.add("hidden");
      $("ask-ok").onclick = null;
      $("ask-cancel").onclick = null;
      resolve(v);
    };
    $("ask-ok").onclick = () => done(true);
    $("ask-cancel").onclick = () => done(false);
  });
}

function fillSelect(el, items, value) {
  if (!el) return;
  if (el.options.length !== items.length) {
    el.innerHTML = items.map((i) => `<option value="${esc(i.id)}">${esc(i.label)}</option>`).join("");
  }
  if (document.activeElement !== el) el.value = value;
}

let lastWakeKey = "";

function renderSettings(d) {
  if (!d) return;
  const s = d.settings || {};
  const w = d.wake || {};
  const wk = $("set-wake");
  if (wk && document.activeElement !== wk) wk.checked = !!s.wake_word;
  if (wk) wk.disabled = !w.available && !s.wake_word;
  const wakeTxt = s.wake_word
    ? (w.running ? `On — ${esc(w.listener_state)}${w.state && w.state !== "idle" ? " · " + esc(w.state) : ""}` : `On — not running ${esc(w.listener_error || "")}`)
    : (w.available ? "Off" : `Unavailable: ${esc(w.reason)}`);
  $("set-wake-status").innerHTML = `${wakeTxt}${w.heard ? `<div class="muted">Last heard: ${esc(w.heard)}</div>` : ""}${w.error ? `<div class="bad-txt">${esc(w.error)}</div>` : ""}`;
  const side = $("wake-side");
  if (side) {
    side.textContent = s.wake_word ? (w.running ? `Hey Jarvis: ${w.state === "idle" ? "listening" : w.state}` : "Hey Jarvis: error") : "Hey Jarvis: off";
    side.classList.toggle("on", !!(s.wake_word && w.running));
  }
  const key = `${w.heard}|${w.reply}`;
  if (s.wake_word && w.reply && key !== lastWakeKey) {
    lastWakeKey = key;
    $("voice-state").textContent = `Heard: ${w.heard}`;
    banner(w.reply);
  }
  fillSelect($("set-stt"), d.stt_engines || [], s.stt_engine);
  const ws = d.whisper || {};
  $("set-whisper-status").innerHTML = !ws.installed
    ? `<span class="bad-txt">Offline engine not installed — using Google</span>`
    : (ws.ready ? `<span class="ok-txt">Offline model ${esc(ws.model)} ready</span> <span class="muted">(${esc(ws.dir)})</span>`
      : (ws.downloading ? `Downloading ${esc(ws.model)}… (about 75 MB)` : `Model ${esc(ws.model)} not downloaded yet — Google is used until it is.${ws.error ? ` <span class="bad-txt">${esc(ws.error)}</span>` : ""}`));
  $("set-whisper-dl").disabled = !ws.installed || ws.ready || ws.downloading;
  fillSelect($("set-voice"), d.voices || [], s.voice);
  $("set-voice-status").innerHTML = d.edge_available
    ? `<span class="muted">Natural voices need internet; Jarvis falls back to the Windows voice offline.</span>`
    : `<span class="bad-txt">Natural voice engine missing — Windows voice only</span>`;
  const m = d.mcp || {};
  const rows = (m.servers || []).map((x) => `<div class="mcp-row"><strong>${esc(x.name)}</strong> ${x.enabled ? `<span class="ok-txt">enabled</span>` : `<span class="muted">disabled</span>`}
      <div class="muted">${esc(x.command)} ${esc((x.args || []).join(" "))}</div>
      ${x.description ? `<div class="muted">${esc(x.description)}</div>` : ""}
      ${x.last_error ? `<div class="bad-txt">${esc(x.last_error)}</div>` : ""}</div>`).join("");
  $("set-mcp").innerHTML = `${rows || `<div class="muted">No MCP servers configured.</div>`}
    ${m.error ? `<div class="bad-txt">Config error: ${esc(m.error)}</div>` : ""}
    <div class="muted">Edit: <code>${esc(m.path)}</code> (example: mcp_servers.example.json). Every MCP tool call asks for your approval.</div>`;
  const scr = d.screen || {};
  $("set-screen").disabled = !scr.available;
  $("cmd-screen").disabled = !scr.available;
}

async function screenFlow() {
  const ok = await ask("R3 · Read my screen",
    "Jarvis will capture your screen once and send a downscaled image to Gemini (or OpenAI) to describe it. Close patient, bank or tax windows first. Nothing is saved.",
    "Capture once");
  if (!ok) return;
  banner("Reading screen…");
  const r = await call("screen_read", "What is on my screen?", true);
  const out = r.ok ? r.data.description : (r.error || "screen read failed");
  banner(r.ok ? "Screen read done" : out);
  if ($("set-screen-out")) $("set-screen-out").textContent = out;
  if (r.ok) {
    $("voice-state").textContent = "Screen described";
    await call("speak", out.slice(0, 400));
  }
}

async function refresh() {
  const [st, met, feed, mem, llms, agents, brief, ready, sets] = await Promise.all([
    call("status"),
    call("metrics"),
    call("feed", 50),
    call("memory"),
    call("llms"),
    call("agents"),
    call("brief"),
    call("readiness"),
    call("settings_get"),
  ]);
  if (sets && sets.ok) renderSettings(sets.data);
  if (st.ok) renderHealth(st.data, agents.ok ? agents.data.agents : [], llms.ok ? llms.data.providers : [], mem.ok ? mem.data : null);
  else banner(st.error || "status offline");
  if (ready && ready.ok) renderReadiness(ready.data);
  else if (core3d) core3d.setHealth(0);
  if (met.ok) renderMetrics(met.data);
  if (feed.ok) renderFeed(feed.data.items, $("feed-search").value);
  if (mem.ok) renderMemory(mem.data);
  if (llms.ok) renderLlms(llms.data.providers);
  if (agents.ok) renderAgents(agents.data.agents);
  if (brief && brief.ok) renderTimeline(brief.data?.text || "");
  else if (st.ok) {
    // brief optional on older bridges
  }
  if (st.ok) $("chk-mute").checked = !!st.data.muted;
}

async function listenFlow() {
  $("voice-state").textContent = "Listening…";
  banner("");
  const r = await call("voice_turn", 6);
  if (!r.ok) {
    banner(r.error || "Could not hear you");
    $("voice-state").textContent = "Voice idle";
    return;
  }
  $("voice-state").textContent = `Heard: ${r.text}`;
  banner(r.reply || "");
  if (r.reply) await call("speak", r.reply);
  $("voice-state").textContent = r.engine === "whisper" ? "Voice idle · offline STT" : "Voice idle";
}

function wire() {
  document.querySelectorAll("#nav button").forEach((b) => {
    b.onclick = () => setRoute(b.dataset.route);
  });
  $("feed-search").oninput = () => refresh();
  $("btn-listen").onclick = listenFlow;
  $("btn-talk").onclick = listenFlow;
  $("btn-stop-voice").onclick = async () => {
    const r = await call("stop_speaking");
    banner(r.ok ? (r.data?.was_speaking ? "Stopped speaking" : "") : (r.error || "stop failed"));
  };
  $("cmd-screen").onclick = screenFlow;
  $("set-screen").onclick = screenFlow;
  $("set-wake").onchange = async () => {
    const el = $("set-wake");
    if (el.checked) {
      const ok = await ask("R3 · Always listen for Hey Jarvis",
        "The microphone will stay open while Jarvis runs. \"Hey Jarvis\" is detected on this PC only; your question is then transcribed and answered. You can turn this off here any time.",
        "Turn on");
      if (!ok) { el.checked = false; return; }
      const r = await call("settings_set", { wake_word: true }, true);
      if (!r.ok) { el.checked = false; banner(r.error || "could not start wake word"); }
      else renderSettings(r.data);
    } else {
      const r = await call("settings_set", { wake_word: false });
      if (r.ok) renderSettings(r.data); else banner(r.error);
    }
  };
  $("set-stt").onchange = async () => {
    const r = await call("settings_set", { stt_engine: $("set-stt").value });
    if (r.ok) renderSettings(r.data); else banner(r.error);
    $("set-stt").blur();
  };
  $("set-voice").onchange = async () => {
    const r = await call("settings_set", { voice: $("set-voice").value });
    if (r.ok) renderSettings(r.data); else banner(r.error);
    $("set-voice").blur();
  };
  $("set-voice-test").onclick = () => call("tts_test");
  $("set-whisper-dl").onclick = async () => {
    const r = await call("stt_download_model");
    banner(r.ok ? "Downloading offline speech model…" : (r.error || "download failed"));
    await refresh();
  };
  $("chk-mute").onchange = async () => {
    const r = await call("mute", $("chk-mute").checked);
    if (!r.ok) banner(r.error);
    await refresh();
  };
  $("cmd-session").onclick = async () => {
    const r = await call("session_start");
    banner(r.ok ? "Session started" : (r.error || "session failed"));
    await refresh();
  };
  $("cmd-calendar").onclick = () => setRoute("calendar");
  $("cmd-voice").onclick = listenFlow;
  $("cmd-dry").onclick = async () => {
    const r = await call("dry_run_workday");
    banner(r.ok ? "Dry-run complete" : (r.error || "dry-run failed"));
    await refresh();
  };
  $("cmd-workday").onclick = () => $("r3-modal").classList.remove("hidden");
  $("r3-cancel").onclick = () => $("r3-modal").classList.add("hidden");
  $("r3-confirm").onclick = async () => {
    $("r3-modal").classList.add("hidden");
    const r = await call("start_workday", true);
    banner(r.ok ? "Workday started" : (r.error || "workday failed"));
    await refresh();
  };
  $("workflows-page").innerHTML = `
    <div class="qcmds">
      <button id="wf-dry">Dry-run Workday</button>
      <button id="wf-real" class="danger">Start Workday (R3)</button>
    </div>`;
  $("wf-dry").onclick = () => $("cmd-dry").click();
  $("wf-real").onclick = () => $("cmd-workday").click();
}

async function loadSkills() {
  const r = await call("skills");
  if (!r.ok) {
    $("skills-page").innerHTML = `<p class="muted">${r.error || "Skills unavailable offline."}</p>`;
    return;
  }
  const items = r.data?.skills || [];
  $("badge-tasks").textContent = String(items.length);
  $("skills-page").innerHTML = items.map((s) =>
    `<div class="feed-item"><strong>${s.name}</strong> · ${s.risk}<div class="muted">${s.summary || ""}</div></div>`
  ).join("") || `<div class="muted">No skills found.</div>`;
  $("tasks-page").innerHTML = $("skills-page").innerHTML;
}

async function boot() {
  mountNavIcons($("nav"));
  core3d = mountCore($("sphere"));
  wire();
  tickClock();
  setInterval(tickClock, 1000);
  const ok = await whenReady(15000);
  if (!ok) {
    banner("Bridge offline — restart JARVIS");
    return;
  }
  await refresh();
  await loadSkills();
  setInterval(refresh, 3000);
}
window.addEventListener("pywebviewready", () => { refresh(); loadSkills(); });
boot();
