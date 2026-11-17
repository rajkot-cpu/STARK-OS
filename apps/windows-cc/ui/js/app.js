// apps/windows-cc/ui/js/app.js
import { call, uiLog, whenReady } from "./bridge.js";
import { mountCore } from "./core3d.js";
import { mountAgentOrbit } from "./orbit3d.js";
import * as v3 from "./v3.js";
import * as p3 from "./p3.js";

let core3d = null;
let agentsOrbit = null;
let selectedAgent = null;
let lastAgentsList = [];

// ---- Voice state for the AI Core (listening while recording, speaking while TTS plays) ----
const voice = { listening: false, speakingUntil: 0, speakStarted: 0, ttsFlag: false, wake: "idle", shown: "",
  wakeEnabled: false, wakeRunning: false };
// Health "Voice" row: say what the mic is really doing (wake word on / stopped / off), never a blanket "Online".
function voiceLabel(muted) {
  if (muted) return ["Muted", "warn"];
  const st = voiceNow();
  if (st === "listening") return ["Listening", "ok"];
  if (st === "speaking") return ["Speaking", "ok"];
  if (voice.wakeEnabled && voice.wakeRunning) return ["Wake on", "ok"];
  if (voice.wakeEnabled) return ["Wake stopped", "warn"];
  return ["Tap to talk", "off"];
}
function markSpeaking(text) {
  const now = Date.now();
  voice.speakStarted = now;
  voice.speakingUntil = now + Math.min(14000, 900 + String(text || "").length * 55);
}
function voiceNow() {
  if (voice.listening || voice.wake === "listening" || voice.wake === "thinking") return "listening";
  if (voice.ttsFlag || voice.wake === "speaking" || Date.now() < voice.speakingUntil) return "speaking";
  return "idle";
}
function pushVoice() {
  const st = voiceNow();
  if (st === voice.shown) return;
  voice.shown = st;
  if (core3d && core3d.setVoice) core3d.setVoice(st);
  if (agentsOrbit && agentsOrbit.setVoice) agentsOrbit.setVoice(st);
  document.body.classList.toggle("voice-listening", st === "listening");
  document.body.classList.toggle("voice-speaking", st === "speaking");
  const sub = document.getElementById("talk-sub");
  if (sub) sub.textContent = st === "listening" ? "I am listening…" : (st === "speaking" ? "Speaking…" : "Tap to talk");
  const el = document.getElementById("hud-voice");
  if (el) {
    el.textContent = st.toUpperCase();
    el.parentElement.classList.toggle("voice-listening", st === "listening");
    el.parentElement.classList.toggle("voice-speaking", st === "speaking");
  }
}
async function speak(text) {
  markSpeaking(text);
  pushVoice();
  return call("speak", text);
}

const $ = (id) => document.getElementById(id);
// Talk-bar status line. kind: "" (neutral info), "warn", "err". The bridge reports a missing/slow
// pywebview API as the bare word "offline"; say what it means instead of a red "offline".
let bannerTimer = 0;
function banner(msg, kind = "") {
  const el = $("banner");
  if (!el) return;
  let text = String(msg || "");
  if (/^(status )?offline$/i.test(text)) { text = "Jarvis core is still starting — retrying…"; kind = "warn"; }
  el.textContent = text;
  el.className = `banner${kind ? " " + kind : ""}`;
  el.title = text;
  clearTimeout(bannerTimer);
  if (text && text !== "…") bannerTimer = setTimeout(() => { if (el.textContent === text) banner(""); }, kind === "err" ? 30000 : 20000);
}
const bannerErr = (msg) => banner(msg, "err");

function setRoute(name) {
  if (name !== "home" && $("page-home") && $("page-home").classList.contains("focus")) setFocus(false);
  document.querySelectorAll("#nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.route === name);
  });
  document.querySelectorAll(".page").forEach((p) => {
    p.classList.toggle("active", p.id === `page-${name}`);
  });
  if (name === "trading") p3.renderTradingLive($("trading-grid"));
  if (name === "tasks") p3.renderTasksP3($("tasks-p3"));
  if (name === "memory") p3.renderMemorySearch($("mem-search"));
  if (name === "settings") { p3.renderSettingsP3(document.querySelector("#page-settings .settings-grid")); p3.refreshSettingsP3(); }
  if (name === "agents") renderDiagram();
  if (name === "safety" || name === "security") refreshSafety();
}

function tickClock() {
  const d = new Date();
  if ($("clock-date")) $("clock-date").textContent = d.toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  $("clock").innerHTML = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true })
    .replace(/\s?(AM|PM)/, ' <small>$1 IST</small>');
}

function renderHealth(status, agents, llms, mem) {
  const connected = (llms || []).filter((p) => p.state === "connected").length;
  const active = (agents || []).filter((a) => a.state === "active").length;
  const muted = !!(status && status.muted);
  const halted = !!(status && status.halted);
  const ram = lastMetrics && lastMetrics.ram_total_gb ? lastMetrics : null;
  const items = [
    ["core", "#38d4ff", "AI Core", halted ? "Halted" : (status?.policy_ok ? "Active" : (status?.system_status || "—")), halted ? "bad" : (status?.policy_ok ? "ok" : "warn"), ""],
    ["brain", "#a77bff", "Memory", ram ? `${ram.ram_used_gb}/${ram.ram_total_gb} GB` : "—", "ok",
      ram ? `<i class="ov-bar"><span style="width:${Math.round(ram.ram_pct)}%"></span></i>` : ""],
    ["mic", "#3dff9a", "Voice", ...voiceLabel(muted), ""],
    ["agents", "#ff9d2e", "Agents", `${active} running`, active ? "ok" : "off", ""],
    ["cpu", "#5b8cff", "LLMs", `${connected} connected`, connected ? "ok" : "bad", ""],
    ["shield", "#19e6c1", "System", halted ? "STOP active" : (status?.quiet_hours ? "Quiet hours" : (status?.policy_ok ? "Optimal" : "Check POLICY")), halted ? "bad" : (status?.policy_ok ? "ok" : "warn"), ""],
  ];
  $("health-list").innerHTML = items.map(([ic, col, k, v, tone, extra]) =>
    `<li class="ov-row"><span class="ov-ic" style="--oc:${col}">${v3.icon(ic)}</span><span class="ov-k">${k}${extra}</span><strong class="ov-v" title="${esc(v)}">${esc(v)}</strong><i class="dot ${tone}"></i></li>`).join("");
  // Quiet hours is a normal, scheduled state (no proactive work / notifications) -> calm amber, not red.
  // Only an unapproved POLICY is an error.
  const pill = $("sys-pill");
  const quiet = !!status?.quiet_hours && !!status?.policy_ok;
  const bad = !status?.policy_ok;
  const low = lastReadyPct !== null && lastReadyPct < 50;
  pill.innerHTML = halted ? "System Status: <b>■ HALTED</b>" : bad ? `System Status: <b>${esc(status?.system_status || "CHECK POLICY")}</b>`
    : (quiet ? "System Status: <b>Quiet hours</b>" : (low ? "System Status: <b>DEGRADED</b>" : "System Status: <b>✓ OPTIMAL</b>"));
  pill.classList.toggle("halted", halted);
  pill.classList.toggle("low", !halted && !bad && !quiet && low);
  pill.title = quiet ? "Quiet hours (POLICY.yaml): Jarvis won't start scheduled work or speak up on its own. Everything you ask still works." : "";
  pill.classList.toggle("bad", bad || halted);
  pill.classList.toggle("quiet", quiet);
  const sys = $("hud-sys");
  if (sys) {
    sys.textContent = bad ? "CHECK POLICY" : (quiet ? "QUIET HOURS" : "ONLINE");
    sys.className = `ht-sys${bad ? " bad" : (quiet ? " quiet" : "")}`;
  }
}

let lastReadyPct = null;
let lastMetrics = null;
const cpuHist = [];
let lastFeedItems = [];
let lastLocalAi = null;
let lastSources = null;
let lastProviders = [];
let lastStatus = null;
let slowAt = 0;
function renderReadiness(data) {
  const pct = Math.max(0, Math.min(100, Math.round(Number(data?.score_pct) || 0)));
  lastReadyPct = pct;
  const ring = $("ready-ring");
  const num = $("g-ready");
  if (num) num.textContent = String(pct);
  if (ring) {
    ring.style.setProperty("--pct", String(pct));
    ring.classList.remove("ready-high", "ready-mid", "ready-low");
    ring.classList.add(pct >= 80 ? "ready-high" : (pct >= 50 ? "ready-mid" : "ready-low"));
  }
  const checks = data?.checks || [];
  const nOk = checks.filter((c) => c.ok).length;
  if ($("ready-summary")) $("ready-summary").innerHTML = checks.length ? `<b>${nOk}</b> of ${checks.length} checks pass` : "";
  const miss = $("ready-miss");
  if (miss) miss.innerHTML = checks.filter((c) => !c.ok).map((c) =>
    `<li><span class="tick">○</span><span>${esc(c.label)}</span><div class="fix">${esc(c.fix)}</div></li>`).join("");
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
  if (agentsOrbit) agentsOrbit.setHealth(pct / 100);
  const arc = $("hud-ready-arc");
  if (arc) {
    arc.setAttribute("stroke-dasharray", `${pct} 100`);
    arc.classList.toggle("mid", pct >= 50 && pct < 80);
    arc.classList.toggle("low", pct < 50);
  }
  if ($("hud-ready")) $("hud-ready").textContent = `${pct}%`;
  const bar = $("hud-ready-bar");
  if (bar) {
    bar.style.width = `${pct}%`;
    const col = pct >= 80 ? "var(--ok)" : (pct >= 50 ? "var(--gold)" : "var(--danger)");
    bar.style.background = col; bar.style.boxShadow = `0 0 6px ${col}`;
  }
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

const goalDrafts = {};
let lastAgentsKey = "";

function renderOrbitDetail() {
  const el = $("orbit-detail");
  if (!el) return;
  const a = (lastAgentsList || []).find((x) => x.id === selectedAgent);
  if (!a) {
    el.innerHTML = `<div class="muted">Click an agent node to see its recent steps.</div>`;
    return;
  }
  const steps = (a.steps || []).slice(-12).map((s) => `<li>${esc(s)}</li>`).join("");
  const det = String(a.detail || "");
  el.innerHTML = `
    <h3>${esc(a.name)} <span class="state-${esc(a.state)}">${esc(a.state)}</span></h3>
    ${a.goal ? `<div class="agent-goal-shown">Goal: ${esc(a.goal.slice(0, 200))}</div>` : `<div class="muted small">No goal yet.</div>`}
    ${det ? `<div class="${a.state === "error" ? "agent-err" : "muted small"}">${esc(det.slice(0, 240))}</div>` : ""}
    ${a.pending ? `<div class="gold small">${esc(a.pending.label)} — waiting for your approval (see its card below)</div>` : ""}
    ${steps ? `<div class="muted small">Recent steps</div><ul class="agent-steps">${steps}</ul>` : `<div class="muted small">No steps yet.</div>`}
    <button class="small" id="orbit-goto">Show card</button>`;
  const b = $("orbit-goto");
  if (b) b.onclick = () => {
    const card = document.querySelector(`#agents-page [data-card-for="${a.id}"]`);
    if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
  };
}

function selectAgent(id, route) {
  selectedAgent = id;
  if (agentsOrbit) agentsOrbit.select(id);
  if (route) setRoute("agents");
  document.querySelectorAll("[data-card-for]").forEach((c) => c.classList.toggle("selected", c.dataset.cardFor === id));
  renderOrbitDetail();
}

function renderAgents(agents) {
  lastAgentsList = agents || [];
  const busy = lastAgentsList.filter((a) => a.state === "active").length;
  if ($("hud-agents")) $("hud-agents").textContent = `${busy} / ${lastAgentsList.length}`;
  if (agentsOrbit) agentsOrbit.update(lastAgentsList);
  if (core3d && core3d.update) core3d.update(lastAgentsList);
  renderOrbitDetail();
  v3.renderAgentsMini($("agents-mini"), lastAgentsList, (id) => selectAgent(id, true));
  renderDiagram();
  const needs = lastAgentsList.filter((a) => a.pending || a.state === "error" || String(a.detail || "").startsWith("needs_r3:")).length;
  const bc = $("bell-count");
  if (bc) { bc.textContent = String(needs); bc.classList.toggle("hidden", !needs); }
  // Keep any goal the operator is typing across the 3s refresh.
  document.querySelectorAll("[data-goal-for]").forEach((el) => { goalDrafts[el.dataset.goalFor] = el.value; });
  const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.goalFor : null;
  const key = JSON.stringify(agents || []);
  if (focused && key === lastAgentsKey) return;
  lastAgentsKey = key;
  const PROV = { gemini: "Gemini", openai: "OpenAI", groq: "Groq" };
  const html = (agents || []).map((a) => {
    const steps = (a.steps || []).slice(-8).map((s) => `<li>${esc(s)}</li>`).join("");
    const det = String(a.detail || "");
    const idx = det.indexOf("needs_r3:");
    const pending = det.startsWith("needs_r3:") ? det.slice(idx + "needs_r3:".length) : "";
    pendingShell[a.id] = pending;
    const reply = esc(a.last_reply || "");
    const files = (a.files || []).map((f) => `<li>${esc(f)}</li>`).join("");
    const isErr = a.state === "error";
    return `
    <div class="agent-card${a.id === selectedAgent ? " selected" : ""}" data-card-for="${a.id}">
      <div>
        <div>${esc(a.name)}</div>
        <div class="state-${a.state}">${esc(a.state)}${a.detail && !isErr ? " · " + esc(det.slice(0, 80)) : ""}</div>
        ${a.goal ? `<div class="agent-goal-shown">Goal: ${esc(a.goal.slice(0, 140))}</div>` : ""}
        ${a.provider ? `<div class="agent-prov">AI: ${esc(PROV[a.provider] || a.provider)}</div>` : ""}
        ${a.notice ? `<div class="agent-notice">⚠ ${esc(a.notice)}</div>` : ""}
        ${isErr ? `<div class="agent-err">${esc(det)}</div>` : ""}
        ${reply && !isErr ? `<div class="muted agent-reply">${reply}</div>` : ""}
        ${files ? `<div class="muted small">Files in ${esc(a.workspace || "workspace")}:</div><ul class="agent-files">${files}</ul>` : ""}
        ${a.folder ? `<button class="small" data-open-folder="${esc(a.folder)}">Open folder</button>` : ""}
        ${steps ? `<ul class="agent-steps">${steps}</ul>` : ""}
        ${a.pending ? `<div class="tool-r3"><div class="gold">${esc(a.pending.label)} — needs your R3 approval</div>
          ${a.pending.args_preview ? `<code>${esc(a.pending.args_preview)}</code>` : ""}
          ${a.pending.kind === "screen" ? `<div class="muted">Jarvis will capture your screen once and describe it. Nothing is saved.</div>` : ""}
          <button data-tool-confirm="${a.id}" data-token="${esc(a.pending.token)}">Approve once</button>
          <button data-tool-reject="${a.id}">Reject</button></div>` : ""}
        ${pending ? `<div class="shell-r3"><div class="muted">Pending shell (R3):</div><code>${esc(pending)}</code>
          <button data-shell-confirm="${a.id}">Confirm shell</button></div>` : ""}
        <input class="agent-goal" data-goal-for="${a.id}" placeholder="Goal — e.g. ${a.id === "builder" ? "build a hello-world page called test-site" : a.id === "video" ? "make a 3D short on today's trend in India" : "what should it do?"}" />
      </div>
      <button data-agent="${a.id}" data-act="${a.state === "active" ? "stop" : "start"}">
        ${a.state === "active" ? "Stop" : "Start"}
      </button>
    </div>`;
  }).join("");
  $("agents-page").innerHTML = html;
  document.querySelectorAll("[data-goal-for]").forEach((el) => {
    const v = goalDrafts[el.dataset.goalFor];
    if (v) el.value = v;
    el.oninput = () => { goalDrafts[el.dataset.goalFor] = el.value; };
    el.onkeydown = (ev) => {
      if (ev.key === "Enter") {
        const btn = el.closest(".agent-card").querySelector("[data-agent]");
        if (btn && btn.dataset.act === "start") btn.click();
      }
    };
  });
  if (focused) {
    const el = document.querySelector(`#page-${document.querySelector(".page.active")?.id?.slice(5) || "home"} [data-goal-for="${focused}"]`);
    if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  }
  document.querySelectorAll("[data-open-folder]").forEach((btn) => {
    btn.onclick = async () => {
      const r = await call("open_folder", btn.dataset.openFolder);
      if (!r.ok) bannerErr(r.error || "could not open folder");
    };
  });
  document.querySelectorAll("[data-shell-confirm]").forEach((btn) => {
    btn.onclick = async () => {
      const cmd = pendingShell[btn.dataset.shellConfirm] || "";
      if (!cmd) return;
      btn.disabled = true;
      const r = await call("shell_confirm", cmd, btn.dataset.shellConfirm);
      banner(r.ok ? "Shell command ran — agent is continuing" : (r.error || `shell failed (rc ${r.data?.returncode ?? "?"})`), r.ok ? "" : "err");
      await refresh();
    };
  });
  document.querySelectorAll("[data-tool-confirm]").forEach((btn) => {
    btn.onclick = async () => {
      btn.disabled = true;
      const r = await call("tool_confirm", btn.dataset.toolConfirm, btn.dataset.token);
      banner(r.ok ? "Approved — agent is continuing" : (r.error || "tool failed"), r.ok ? "" : "err");
      await refresh();
    };
  });
  document.querySelectorAll("[data-tool-reject]").forEach((btn) => {
    btn.onclick = async () => {
      await call("tool_reject", btn.dataset.toolReject);
      banner("Rejected — agent was told and is continuing");
      await refresh();
    };
  });
  document.querySelectorAll("[data-agent]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.agent;
      const act = btn.dataset.act;
      const goal = (goalDrafts[id] || "").trim();
      const r = act === "start"
        ? await call("agent_start", id, goal)
        : await call("agent_stop", id);
      if (!r.ok) bannerErr(r.error || "agent error");
      else if (act === "start") goalDrafts[id] = "";
      lastAgentsKey = "";
      await refresh();
    };
  });
}

async function runCommand(text) {
  const t = (text || "").trim();
  if (!t) return;
  banner("…");
  const r = await call("command", t);
  if (!r.ok) { bannerErr(r.error || "command failed"); uiLog("warn", `command ${JSON.stringify(t)} failed: ${r.error}`, "cmd-bar"); return; }
  const d = r.data || {};
  banner(d.reply || "");
  if (d.reply) speak(d.reply);
  if (d.routed === "agent" && d.started) { lastAgentsKey = ""; await refresh(); }
  if (d.routed === "halt" || d.routed === "resume") { if (d.routed === "halt") banner(d.reply, "err"); await refresh(); }
}

// "2026-11-11T00:52:30.067952+05:30" -> "11 Nov 00:52:30" (today: just the time).
function shortTime(v) {
  const m = /^(\d{4})-(\d\d)-(\d\d)[T ](\d\d:\d\d:\d\d)/.exec(String(v || ""));
  if (!m) return String(v || "");
  const d = new Date();
  const today = Number(m[1]) === d.getFullYear() && Number(m[2]) === d.getMonth() + 1 && Number(m[3]) === d.getDate();
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1];
  return today ? m[4].slice(0, 5) : `${Number(m[3])} ${mon} ${m[4].slice(0, 5)}`;
}

function renderFeed(items, filter) {
  const q = (filter || "").toLowerCase();
  const rows = (items || []).filter((it) => {
    const s = JSON.stringify(it).toLowerCase();
    return !q || s.includes(q);
  }).slice().reverse();
  lastFeedItems = items || [];
  $("feed-list").innerHTML = rows.map((it) => {
    const v = v3.feedView(it);
    return `<div class="feed-item fx"><span class="fx-ic c-${v.color}">${v3.icon(v.icon)}</span><div class="fx-body"><div class="fx-top"><b>${esc(v.title)}</b><span class="t">${esc(shortTime(v.time))}</span></div><div class="msg">${esc(v.sub.slice(0, 160))}</div></div></div>`;
  }).join("") || `<div class="muted">No audit events yet.</div>`;
  $("conv-page").innerHTML = $("feed-list").innerHTML;
  const today = lastFeedItems.filter((it) => v3.isToday(it.time || it.ts_ist)).length;
  if ($("badge-conv")) $("badge-conv").textContent = String(today);
  v3.renderMission($("mission"), lastFeedItems, shortTime);
}

function renderMetrics(m) {
  if (!m) return;
  lastMetrics = m;
  $("g-cpu").textContent = Math.round(m.cpu_pct ?? 0);
  $("g-ram").textContent = Math.round(m.ram_pct ?? 0);
  $("g-disk").textContent = Math.round(m.disk_pct ?? 0);
  v3.setRing("rg-cpu", m.cpu_pct); v3.setRing("rg-ram", m.ram_pct); v3.setRing("rg-disk", m.disk_pct);
  // network ring: share of 100 Mbit/s (12.5 MB/s); the label is the real rate
  v3.setRing("rg-net", m.net_bps == null ? 0 : (m.net_bps / 13107200) * 100);
  const rate = v3.fmtRate(m.net_bps);
  if ($("g-net")) $("g-net").textContent = rate;
  if ($("ft-net")) $("ft-net").textContent = m.net_bps == null ? "measuring…" : rate;
  if ($("g-uptime")) $("g-uptime").textContent = m.uptime_s != null ? v3.fmtUptime(m.uptime_s) : "—";
  cpuHist.push(Number(m.cpu_pct) || 0);
  if (cpuHist.length > 40) cpuHist.shift();
  v3.spark($("cpu-spark"), cpuHist);
}

function renderMemory(mem) {
  const nodes = mem?.nodes ?? 0;
  const edges = mem?.edges ?? 0;
  const sources = (mem?.sources || []).join(", ") || "none";
  const last = (mem?.recent || [])[0];
  $("memory-stats").innerHTML = `<div class="mi-big"><b>${nodes}</b> memory files</div><div>${v3.fmtBytes(mem?.bytes)} indexed · ${edges} links</div>` +
    `<div class="muted">Sources: ${esc(sources)}</div>${last ? `<div class="muted">Latest: ${esc(last)}</div>` : ""}`;
  $("memory-page").innerHTML = `<div class="muted small">Indexed from STATE.md, journal, memory, notes and reports in the Jarvis folder. Counts are live; nothing here is sample data.</div>`;
  v3.renderMemoryMap($("mem-svg"), mem);
  const bys = Object.entries(mem?.by_source || {});
  const mx = Math.max(1, ...bys.map(([, n]) => n));
  if ($("mf-an")) $("mf-an").innerHTML = bys.length ? bys.map(([k, n]) => `<div class="mf-bar"><span>${esc(k)}</span><i><b style="width:${(n / mx) * 100}%"></b></i><em>${n}</em></div>`).join("") : `<span class="muted">No memory sources found yet.</span>`;
  const found = (mem?.sources || []).length, cand = mem?.candidates || 5;
  if ($("mf-ring")) { $("mf-ring").style.setProperty("--pct", String(Math.round((found / cand) * 100))); $("mf-ring-n").textContent = `${found}/${cand}`; }
  if ($("mf-ring-t")) $("mf-ring-t").textContent = "memory sources present";
  const memAgent = (lastAgentsList || []).find((a) => a.id === "memory");
  if ($("mf-proc")) $("mf-proc").innerHTML = `<div>Memory agent: <b>${esc(memAgent ? memAgent.state : "—")}</b></div><div>Agents active: <b>${(lastAgentsList || []).filter((a) => a.state === "active").length}</b></div><div class="muted">${esc(memAgent && memAgent.goal ? "Goal: " + memAgent.goal.slice(0, 80) : "No memory task running.")}</div>`;
  $("knowledge-page").innerHTML = `<p class="muted">Indexed sources: ${sources}</p>`;
}

function renderLlms(providers) {
  // Show the provider Jarvis actually tries first (agents: Gemini -> OpenAI -> Groq).
  const rank = (n) => { const i = ["gemini", "openai", "groq"].indexOf(String(n || "").toLowerCase()); return i < 0 ? 9 : i; };
  const live = (providers || []).filter((p) => p.state === "connected").sort((a, b) => rank(a.name) - rank(b.name))[0];
  if ($("hud-provider")) $("hud-provider").textContent = live ? String(live.name).toUpperCase() : "OFFLINE";
  lastProviders = providers || [];
  v3.renderLlmRows($("llm-grid"), lastProviders, lastLocalAi);
  v3.renderLlmRows($("set-providers"), lastProviders, lastLocalAi);
  const nKey = lastProviders.filter((p) => p.state !== "missing_key").length;
  if ($("prov-keys")) $("prov-keys").textContent = `${nKey} cloud provider key(s) set · local: ${lastLocalAi && lastLocalAi.ollama ? ({ ready: "Ollama ready", no_models: "Ollama installed, no models", not_running: "Ollama not running", not_installed: "no Ollama" })[lastLocalAi.ollama.state] || "—" : "checking…"}`;
}

function renderTimeline(briefText) {
  const lines = (briefText || "").split("\n").filter(Boolean).slice(0, 40);
  $("timeline").innerHTML = lines.length
    ? lines.map((l) => `<div class="feed-item">${esc(l)}</div>`).join("")
    : `<div class="muted">No brief for today yet.</div>`;
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
  banner(r.ok ? "Screen read done" : out, r.ok ? "" : "err");
  if ($("set-screen-out")) $("set-screen-out").textContent = out;
  if (r.ok) {
    $("voice-state").textContent = "Screen described";
    await speak(out.slice(0, 400));
  }
}

// ---- Emergency STOP / Safety page (Master Upgrade Module 1) ----
let haltState = null;
function renderHalt(h) {
  if (!h) return;
  haltState = h;
  const on = !!h.stopped;
  document.body.classList.toggle("halted", on);
  const b = $("halt-banner");
  if (b) b.classList.toggle("hidden", !on);
  const via = { hotkey: "the hotkey", command: "a typed command", voice: "voice", stop_file: "the STOP file", button: "the STOP button" }[h.source] || h.source || "STOP";
  const since = h.since ? new Date(h.since).toLocaleTimeString() : "";
  const detail = on
    ? (h.stop_file_present ? `STOP file present — delete ${h.stop_file} to allow resume.` : `Since ${since} via ${via}. Nothing restarts until you resume.`)
    : "";
  if ($("hb-detail")) $("hb-detail").textContent = detail;
  if ($("hb-resume")) $("hb-resume").disabled = !h.can_resume;
  if ($("sf-state")) {
    $("sf-state").textContent = on ? "STANDBY — HALTED" : "ARMED — READY";
    $("sf-state").classList.toggle("halted", on);
  }
  if ($("sf-since")) $("sf-since").textContent = on ? `Stopped ${since} via ${via}${h.reason ? " · " + h.reason : ""}` : "No STOP active.";
  if ($("sf-report")) {
    const rep = h.report || {};
    $("sf-report").innerHTML = on && Object.keys(rep).length
      ? Object.entries(rep).map(([k, v]) => `<div>${esc(k.replace(/_/g, " "))}: <b>${esc(v)}</b></div>`).join("")
      : "";
  }
  if ($("sf-resume")) $("sf-resume").disabled = !h.can_resume;
  if ($("sf-resume-note")) $("sf-resume-note").textContent = on && h.stop_file_present ? "Delete the STOP file first." : (on ? "" : "Nothing to resume.");
  if ($("sf-stopfile")) $("sf-stopfile").textContent = h.stop_file || "";
  if ($("ft-safety")) { $("ft-safety").textContent = on ? "STOP active" : "Armed"; $("ft-safety").className = on ? "bad-txt" : "ok-txt"; }
  if ($("sf-hotkey") && h.hotkey) {
    const hk = h.hotkey.state;
    $("sf-hotkey").textContent = hk === "active" ? "active" : hk === "failed" ? `not available (${h.hotkey.error || "in use"})` : hk;
  }
}

function renderSafety(d) {
  if (!d) return;
  renderHalt(d.halt);
  const a = d.audit || {};
  if ($("sf-audit")) {
    $("sf-audit").innerHTML = a.ok
      ? `Audit log intact · ${a.chained} chained of ${a.lines} lines (${a.legacy} older unchained)`
      : `<span class="err-text">Audit log check FAILED: ${esc((a.problems || []).map((p) => `line ${p.line}: ${p.problem}`).join("; "))}</span>`;
  }
  const k = d.secrets || {};
  if ($("sf-keys")) {
    $("sf-keys").textContent = !k.credential_manager
      ? "Windows Credential Manager not available; keys stay in secrets\\api_keys.env."
      : `${k.in_credential_manager} key(s) in Windows Credential Manager · ${k.plaintext_in_file} still in api_keys.env` +
        ((k.missing_from_store || []).length ? ` · missing: ${k.missing_from_store.join(", ")}` : "");
  }
  if ($("sf-levels")) {
    $("sf-levels").innerHTML = (d.levels || []).map((l) =>
      `<div class="sf-level"><span class="tier">${esc(l.tier)}</span><b>Level ${l.level} · ${esc(l.name)}</b><div class="muted">${esc(l.rule)}</div>` +
      `<div>${(l.actions || []).map((x) => `<code>${esc(x)}</code>`).join(" ")}</div>` +
      ((l.not_enabled || []).length ? `<div class="muted">Not enabled in Jarvis yet: ${l.not_enabled.map(esc).join(", ")}</div>` : "") +
      `</div>`).join("");
  }
}

async function emergencyStop(source) {
  const r = await call("halt_stop", source || "button");
  if (r && r.ok) {
    renderHalt(r.data);
    banner("EMERGENCY STOP — all automation halted.", "err");
  } else bannerErr(`STOP failed: ${(r && r.error) || "no response"} — use Ctrl+Alt+Shift+S or create the STOP file`);
  refresh();
}

function resumeFlow() {
  $("resume-err").textContent = "";
  $("resume-input").value = "";
  $("resume-modal").classList.remove("hidden");
  setTimeout(() => $("resume-input").focus(), 50);
  const close = () => $("resume-modal").classList.add("hidden");
  const go = async () => {
    const r = await call("halt_resume", $("resume-input").value);
    if (r && r.ok) {
      close();
      renderHalt(r.data);
      banner("Resumed. Stopped tasks were not restarted.");
      refresh();
    } else $("resume-err").textContent = (r && r.error) || "Could not resume";
  };
  $("resume-ok").onclick = go;
  $("resume-cancel").onclick = close;
  $("resume-input").onkeydown = (ev) => { if (ev.key === "Enter") go(); if (ev.key === "Escape") close(); };
}

async function refreshSafety() {
  const r = await call("safety_info");
  if (r && r.ok) {
    renderSafety(r.data);
    v3.renderShield($("shield-svg"), $("sec-cards"), r.data, lastStatus ? lastStatus.policy_ok : undefined);
  }
}

function renderDiagram() {
  const live = (lastProviders || []).filter((p) => p.state === "connected")[0];
  if ($("page-agents") && $("page-agents").classList.contains("active")) v3.renderNetDiagram($("nd-svg"), lastAgentsList, live ? live.name : "");
}

// slower, read-only extras (local AI, data sources): every 30 s
async function refreshSlow() {
  const [la, src, info] = await Promise.all([call("local_ai"), call("sources"), slowAt ? null : call("app_info")]);
  slowAt = Date.now();
  if (la && la.ok && la.data && la.data.ollama) { lastLocalAi = la.data; renderLlms(lastProviders); }
  if (src && src.ok && src.data && Array.isArray(src.data.sources)) { lastSources = src.data.sources; v3.renderSources($("nd-sources"), lastSources); }
  if (info && info.ok) {
    if ($("app-version")) $("app-version").textContent = `v${info.data.version}`;
    if ($("operator-name")) $("operator-name").textContent = info.data.operator;
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
  if (st && st.ok) lastStatus = st.data;
  if (Date.now() - slowAt > 30000) refreshSlow();
  if ($("page-tasks") && $("page-tasks").classList.contains("active")) p3.loadTasks();
  const hs = await call("halt_status");
  if (hs && hs.ok) renderHalt(hs.data);
  if (["safety", "security"].some((r) => $(`page-${r}`) && $(`page-${r}`).classList.contains("active"))) refreshSafety();
  if (sets && sets.ok) {
    renderSettings(sets.data);
    voice.ttsFlag = !!sets.data.speaking;
    voice.wake = (sets.data.settings && sets.data.settings.wake_word && sets.data.wake && sets.data.wake.state) || "idle";
    voice.wakeEnabled = !!(sets.data.settings && sets.data.settings.wake_word);
    voice.wakeRunning = !!(sets.data.wake && sets.data.wake.running);
    if (!voice.ttsFlag && Date.now() - voice.speakStarted > 2500) voice.speakingUntil = 0;
    pushVoice();
  }
  if (met.ok) renderMetrics(met.data);
  if (st.ok) {
    renderHealth(st.data, agents.ok ? agents.data.agents : [], llms.ok ? llms.data.providers : [], mem.ok ? mem.data : null);
    if (/still starting|not responding/.test($("banner").textContent)) banner("");
  } else banner(st.error === "offline" ? "offline" : `Jarvis core not responding (${st.error || "status"}) — retrying`, "warn");
  if (ready && ready.ok) renderReadiness(ready.data);
  else if (core3d) core3d.setHealth(0);
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
  voice.listening = true;
  pushVoice();
  let r;
  try { r = await call("voice_turn", 6); } finally { voice.listening = false; pushVoice(); }
  if (!r.ok) {
    bannerErr(r.error || "Could not hear you");
    $("voice-state").textContent = "Voice idle";
    return;
  }
  $("voice-state").textContent = `Heard: ${r.text}`;
  banner(r.reply || "");
  if (r.routed === "agent") { lastAgentsKey = ""; refresh(); }
  if (r.reply) await speak(r.reply);
  $("voice-state").textContent = r.engine === "whisper" ? "Voice idle · offline STT" : "Voice idle";
}

function setFocus(on) {
  const page = $("page-home");
  if (!page) return;
  page.classList.toggle("focus", !!on);
  const b = $("btn-focus");
  if (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); b.querySelector(".fx-txt").textContent = on ? "Exit focus" : "Focus"; }
  if (core3d && core3d.relayout) core3d.relayout();
}

function wire() {
  $("btn-focus").onclick = () => setFocus(!$("page-home").classList.contains("focus"));
  $("more-cue").onclick = () => $("home-more").scrollIntoView({ behavior: "smooth", block: "start" });
  document.addEventListener("keydown", (ev) => {
    const t = ev.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (!$("page-home").classList.contains("active")) return;
    if (ev.key === "Escape" && $("page-home").classList.contains("focus")) setFocus(false);
    else if ((ev.key === "f" || ev.key === "F") && !ev.ctrlKey && !ev.altKey && !ev.metaKey) setFocus(!$("page-home").classList.contains("focus"));
  });
  document.querySelectorAll("#nav button").forEach((b) => {
    b.onclick = () => setRoute(b.dataset.route);
  });
  $("btn-estop").onclick = () => emergencyStop("button");
  $("btn-focus-side").onclick = () => { setRoute("home"); setFocus(!$("page-home").classList.contains("focus")); };
  $("top-grid").onclick = () => setRoute("skills");
  $("top-settings").onclick = () => setRoute("settings");
  $("top-bell").onclick = () => setRoute("agents");
  $("feed-all").onclick = () => setRoute("conversations");
  $("agents-all").onclick = () => setRoute("agents");
  $("mem-details").onclick = () => setRoute("memory");
  document.querySelectorAll("[data-goto]").forEach((b) => { b.onclick = () => setRoute(b.dataset.goto); });
  $("q-task").onclick = () => { setRoute("home"); $("cmd-input").focus(); };
  $("q-workflow").onclick = () => setRoute("workflows");
  $("q-folder").onclick = async () => { const r = await call("open_folder", "workspace"); if (!r.ok) bannerErr(r.error || "could not open workspace"); };
  $("btn-brief").onclick = async () => {
    const r = await call("brief");
    const text = r && r.ok ? String(r.data?.text || "").trim() : "";
    if (!text) { banner("No brief for today yet — Session Start or Dry-run Workday writes one.", "warn"); return; }
    banner("Executive briefing…");
    speak(text.replace(/[#*_`>|-]+/g, " ").replace(/\s+/g, " ").slice(0, 700));
  };
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && !ev.altKey && !ev.shiftKey && (ev.key === "k" || ev.key === "K")) { ev.preventDefault(); $("feed-search").focus(); }
  });
  // In-window fallback for the STOP hotkey (the global one is registered by Python).
  document.addEventListener("keydown", (ev) => {
    if (ev.ctrlKey && ev.altKey && ev.shiftKey && (ev.key === "S" || ev.key === "s")) {
      if (!(haltState && haltState.hotkey && haltState.hotkey.state === "active")) { ev.preventDefault(); emergencyStop("hotkey"); }
    }
  }, true);
  $("sf-stop").onclick = () => emergencyStop("button");
  $("hb-resume").onclick = resumeFlow;
  $("sf-resume").onclick = resumeFlow;
  $("sf-verify").onclick = refreshSafety;
  $("feed-search").oninput = () => refresh();
  $("btn-listen").onclick = listenFlow;
  $("btn-talk").onclick = listenFlow;
  $("btn-stop-voice").onclick = async () => {
    const r = await call("stop_speaking");
    banner(r.ok ? (r.data?.was_speaking ? "Stopped speaking" : "") : (r.error || "stop failed"), r.ok ? "" : "err");
  };
  $("cmd-screen").onclick = screenFlow;
  $("cmd-bar").onsubmit = async (ev) => {
    ev.preventDefault();
    const v = $("cmd-input").value;
    $("cmd-input").value = "";
    await runCommand(v);
  };
  $("cmd-mic").onclick = listenFlow;
  $("set-screen").onclick = screenFlow;
  $("set-wake").onchange = async () => {
    const el = $("set-wake");
    if (el.checked) {
      const ok = await ask("R3 · Always listen for Hey Jarvis",
        "The microphone will stay open while Jarvis runs. \"Hey Jarvis\" is detected on this PC only; your question is then transcribed and answered. You can turn this off here any time.",
        "Turn on");
      if (!ok) { el.checked = false; return; }
      const r = await call("settings_set", { wake_word: true }, true);
      if (!r.ok) { el.checked = false; bannerErr(r.error || "could not start wake word"); }
      else renderSettings(r.data);
    } else {
      const r = await call("settings_set", { wake_word: false });
      if (r.ok) renderSettings(r.data); else bannerErr(r.error);
    }
  };
  $("set-stt").onchange = async () => {
    const r = await call("settings_set", { stt_engine: $("set-stt").value });
    if (r.ok) renderSettings(r.data); else bannerErr(r.error);
    $("set-stt").blur();
  };
  $("set-voice").onchange = async () => {
    const r = await call("settings_set", { voice: $("set-voice").value });
    if (r.ok) renderSettings(r.data); else bannerErr(r.error);
    $("set-voice").blur();
  };
  $("set-voice-test").onclick = () => call("tts_test");
  $("set-whisper-dl").onclick = async () => {
    const r = await call("stt_download_model");
    banner(r.ok ? "Downloading offline speech model…" : (r.error || "download failed"), r.ok ? "" : "err");
    await refresh();
  };
  $("chk-mute").onchange = async () => {
    const r = await call("mute", $("chk-mute").checked);
    if (!r.ok) bannerErr(r.error);
    await refresh();
  };
  $("cmd-session").onclick = async () => {
    const r = await call("session_start");
    banner(r.ok ? "Session started" : (r.error || "session failed"), r.ok ? "" : "err");
    await refresh();
  };
  $("cmd-calendar").onclick = () => setRoute("calendar");
  $("cmd-voice").onclick = listenFlow;
  $("cmd-dry").onclick = async () => {
    const r = await call("dry_run_workday");
    banner(r.ok ? "Dry-run complete" : (r.error || "dry-run failed"), r.ok ? "" : "err");
    await refresh();
  };
  $("cmd-workday").onclick = () => $("r3-modal").classList.remove("hidden");
  $("r3-cancel").onclick = () => $("r3-modal").classList.add("hidden");
  $("r3-confirm").onclick = async () => {
    $("r3-modal").classList.add("hidden");
    const r = await call("start_workday", true);
    banner(r.ok ? "Workday started" : (r.error || "workday failed"), r.ok ? "" : "err");
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
}

// Visible message instead of a blank panel when WebGL is unavailable or its context is lost.
function glFallback(canvas, what) {
  if (!canvas || !canvas.parentNode) return;
  if (canvas.parentNode.querySelector(".gl-fallback")) return;
  const d = document.createElement("div");
  d.className = "gl-fallback";
  d.textContent = `3D ${what} unavailable — WebGL could not start on this PC (see logs\\ui-errors.log). Agents still work below.`;
  canvas.style.display = "none";
  canvas.parentNode.insertBefore(d, canvas.nextSibling);
}

async function boot() {
  window.__jarvisBooted = true;
  try { v3.mountIcons(document); } catch (e) { uiLog("error", `v3 icons: ${e && e.stack ? e.stack : e}`, "boot"); }
  // v3: flat neon SVG nav icons. The old per-button WebGL icons used one WebGL context each (16 with the
  // new pages, Chromium's limit), so they are no longer mounted; only the hero core and agent orbit use WebGL.
  try { v3.mountNavSvg($("nav")); } catch (e) { uiLog("error", `nav icons: ${e && e.stack ? e.stack : e}`, "boot"); }
  // Home AI Core: agents orbit it as 3D nodes (falls back to the plain core, then to a message).
  try {
    core3d = mountAgentOrbit($("sphere"), { host: $("core-stage"), labels: $("home-orbit-labels"), padTop: 44, padBottom: 8,
      obstacles: () => [...document.querySelectorAll("#core-stage .hud-chip, #core-stage .hud-title, #btn-focus, #greet, #core-stage .core-caption")],
      onSelect: (id) => selectAgent(id, true),
      onLost: () => glFallback($("sphere"), "AI Core") });
    if (!core3d.ok) core3d = mountCore($("sphere"));
    if (core3d && core3d.ok === false) glFallback($("sphere"), "AI Core");
  } catch (e) {
    uiLog("error", `AI Core mount: ${e && e.stack ? e.stack : e}`, "boot");
    glFallback($("sphere"), "AI Core");
    core3d = null;
  }
  try {
    agentsOrbit = mountAgentOrbit($("agents-orbit"), { labels: $("orbit-labels"), padTop: 12, padBottom: 26,
      obstacles: () => [...document.querySelectorAll(".orbit-stage .orbit-legend")],
      onSelect: (id) => selectAgent(id, false), onLost: () => glFallback($("agents-orbit"), "agent orbit") });
    if (!agentsOrbit.ok) { glFallback($("agents-orbit"), "agent orbit"); agentsOrbit = null; }
  } catch (e) {
    uiLog("error", `agent orbit mount: ${e && e.stack ? e.stack : e}`, "boot");
    glFallback($("agents-orbit"), "agent orbit");
    agentsOrbit = null;
  }
  wire();
  setInterval(pushVoice, 250);
  tickClock();
  setInterval(tickClock, 1000);
  startPolling();
}

// The pywebview bridge can take 40-60 s to come up on a cold start. Wait for it (no dead end), show a
// neutral "starting" note meanwhile, and start the 3 s refresh exactly once whichever path wins.
let polling = false;
async function startPolling() {
  if (polling) return;
  let ok = await whenReady(15000);
  while (!ok) {
    banner("Jarvis core is still starting — retrying…", "warn");
    ok = await whenReady(15000);
  }
  if (polling) return;
  polling = true;
  if (/still starting/.test($("banner").textContent)) banner("");
  window.__jarvisPolling = true;
  await refresh();
  await loadSkills();
  setInterval(refresh, 3000);
}
window.addEventListener("pywebviewready", () => { startPolling(); });
boot();
