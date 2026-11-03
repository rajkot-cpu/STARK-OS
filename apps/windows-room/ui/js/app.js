// apps/windows-room/ui/js/app.js — live bindings for the workshop plates
import { whenReady, call } from "./bridge.js";
import { buildRoom } from "./scene.js";

const room = buildRoom(document.getElementById("scene"));
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// Clicks/scroll on plates must not orbit the camera.
for (const p of Object.values(room.plates)) {
  for (const ev of ["pointerdown", "wheel", "touchstart"]) p.el.addEventListener(ev, (e) => e.stopPropagation());
}

let bannerTimer;
export function banner(msg) {
  const b = $("banner");
  clearTimeout(bannerTimer);
  if (!msg) return b.classList.add("hidden");
  b.textContent = msg;
  b.classList.remove("hidden");
  bannerTimer = setTimeout(() => b.classList.add("hidden"), 6000);
}

const state = { muted: false };

function setFlag(id, val, goodWhen = true) {
  const el = $(id);
  el.textContent = val === undefined ? "—" : val ? "yes" : "no";
  el.className = val === undefined ? "" : val === goodWhen ? "ok" : "bad";
}

async function refreshStatus() {
  const r = await call("status");
  if (!r.ok) {
    $("st-system").textContent = r.error === "offline" ? "OFFLINE" : "ERROR";
    $("st-system").className = "bad";
    return;
  }
  const d = r.data;
  $("st-system").textContent = String(d.system_status || "—").toUpperCase();
  $("st-system").className = d.policy_ok ? "ok" : "bad";
  setFlag("st-policy", d.policy_ok);
  setFlag("st-quiet", d.quiet_hours, false);
  setFlag("st-muted", d.muted, false);
  $("st-today").textContent = d.today || "—";
  state.muted = !!d.muted;
  const mb = $("btn-mute");
  if (mb) mb.textContent = state.muted ? "Unmute" : "Mute";
}

async function refreshLlms() {
  const r = await call("llms");
  const ul = $("llms");
  const rows = (r.ok && r.data.providers) || [];
  if (!rows.length) { ul.innerHTML = `<li class="empty">${esc(r.ok ? "No providers" : r.error)}</li>`; return; }
  ul.innerHTML = rows.map((p) =>
    `<li><span><i class="dot ${p.state === "connected" ? "ok" : "bad"}"></i>${esc(p.name || p.id)}</span><small>${esc(p.state)}</small></li>`).join("");
}

export function agentRow(a) {
  const on = a.state === "active";
  return `<li><span><i class="dot ${on ? "ok" : a.state === "error" ? "bad" : ""}"></i>${esc(a.name || a.id)}</span>` +
    `<span><small>${esc(a.state)}</small> <button data-agent="${esc(a.id)}" data-op="${on ? "agent_stop" : "agent_start"}">${on ? "Stop" : "Start"}</button></span></li>`;
}

async function refreshAgents() {
  const r = await call("agents");
  const rows = (r.ok && r.data.agents) || [];
  $("agents").innerHTML = rows.length ? rows.map(agentRow).join("") : `<li class="empty">${esc(r.ok ? "No agents" : r.error)}</li>`;
}

async function refreshFeed() {
  const r = await call("feed", 20);
  const items = ((r.ok && r.data.items) || []).slice().reverse();
  $("feed").innerHTML = items.length
    ? items.map((e) => `<li>${esc(e.ts || e.time || "")} ${esc(e.action || e.event || e.type || e.raw || JSON.stringify(e))}</li>`).join("")
    : `<li class="empty">${esc(r.ok ? "No audit events yet" : r.error)}</li>`;
}

async function refreshSkills() {
  const r = await call("skills");
  const rows = (r.ok && r.data.skills) || [];
  $("skills").innerHTML = rows.length
    ? rows.map((k) => `<li title="${esc(k.summary)}"><b>${esc(k.name)}</b> <small>[${esc(k.risk)}]</small></li>`).join("")
    : `<li class="empty">${esc(r.ok ? "No skills loaded" : r.error)}</li>`;
}

async function action(btn, method, args = [], okMsg) {
  btn.disabled = true;
  try {
    const r = await call(method, ...args);
    banner(r.ok ? okMsg || `${method}: ok` : `${method} failed: ${r.error}`);
    await refresh();
    return r;
  } finally {
    btn.disabled = false;
  }
}

export async function refresh() {
  await Promise.all([refreshStatus(), refreshAgents(), refreshFeed()]);
}

// Hybrid voice: bridge.voice_turn = listen → local "Yes sir" → Gemini reply. No echo.
async function voiceFlow() {
  const btn = $("btn-mic");
  btn.disabled = true; btn.classList.add("live");
  $("voice-state").textContent = "Listening…";
  room.setPulse(1);
  try {
    const r = await call("voice_turn", 6);
    if (r.text) $("voice-heard").textContent = r.text;
    if (!r.ok) { $("voice-state").textContent = r.error || "Could not hear you"; return; }
    $("voice-reply").textContent = r.reply || "—";
    $("voice-state").textContent = "Speaking…";
    room.setPulse(0.5);
    if (r.reply) await call("speak", r.reply);
    $("voice-state").textContent = "Voice idle";
  } finally {
    room.setPulse(0);
    btn.disabled = false; btn.classList.remove("live");
  }
}

function wire() {
  $("btn-mic").onclick = voiceFlow;
  $("btn-session").onclick = (e) => action(e.currentTarget, "session_start", [], "Session started");
  $("btn-dry").onclick = (e) => action(e.currentTarget, "dry_run_workday", [], "Dry-run complete");
  $("btn-mute").onclick = (e) => action(e.currentTarget, "mute", [!state.muted]);
  // R3: Start Workday only after explicit modal confirmation.
  $("btn-workday").onclick = () => $("r3").classList.remove("hidden");
  $("r3-cancel").onclick = () => $("r3").classList.add("hidden");
  $("r3-ok").onclick = async (e) => {
    $("r3").classList.add("hidden");
    await action(e.currentTarget, "start_workday", [true], "Workday started");
  };
  $("agents").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-agent]");
    if (b) action(b, b.dataset.op, [b.dataset.agent]);
  });
}

wire();
whenReady().then((ok) => {
  if (!ok) banner("Bridge offline — open via JarvisRoom host (host_main.py)");
  refresh(); refreshLlms(); refreshSkills();
  setInterval(refresh, 3000);
  setInterval(refreshLlms, 30000); // provider probes hit the network; keep slow
});
