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
  return `<li><span><i class="dot ${a.state === "active" ? "ok" : a.state === "error" ? "bad" : ""}"></i>${esc(a.name || a.id)}</span><small>${esc(a.state)}</small></li>`;
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
}

wire();
whenReady().then((ok) => {
  if (!ok) banner("Bridge offline — open via JarvisRoom host (host_main.py)");
  refresh(); refreshLlms();
  setInterval(refresh, 3000);
  setInterval(refreshLlms, 30000); // provider probes hit the network; keep slow
});
