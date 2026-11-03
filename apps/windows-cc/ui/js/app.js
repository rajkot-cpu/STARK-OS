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
  const score = (ok ? 0.5 : 0.2) + Math.min(0.4, connected * 0.08) + Math.min(0.2, active * 0.05);
  if (core3d) core3d.setHealth(score);
  $("core-page").innerHTML = $("health-list").innerHTML;
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

async function refresh() {
  const [st, met, feed, mem, llms, agents, brief] = await Promise.all([
    call("status"),
    call("metrics"),
    call("feed", 50),
    call("memory"),
    call("llms"),
    call("agents"),
    call("brief"),
  ]);
  if (st.ok) renderHealth(st.data, agents.ok ? agents.data.agents : [], llms.ok ? llms.data.providers : [], mem.ok ? mem.data : null);
  else banner(st.error || "status offline");
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
  $("voice-state").textContent = "Voice idle";
}

function wire() {
  document.querySelectorAll("#nav button").forEach((b) => {
    b.onclick = () => setRoute(b.dataset.route);
  });
  $("feed-search").oninput = () => refresh();
  $("btn-listen").onclick = listenFlow;
  $("btn-talk").onclick = listenFlow;
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
