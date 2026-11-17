// apps/windows-cc/ui/js/v3.js — Command Center v3 HUD pieces (reference-mockup restyle).
// Everything shown here comes from the bridge (real data) or says plainly that it is not connected.
// No canvases: SVG + CSS only, so the canvas budget (hero core + agent orbit + nav icons) is unchanged.

const P = {
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-4.3-4.3",
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  bell: "M6 16V11a6 6 0 1 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 13a7.5 7.5 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-1.7-1L15 3.5h-4L10.7 6a7 7 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.3 2.5h4l.3-2.5a7 7 0 0 0 1.7-1l2.4 1 2-3.4z",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
  plus: "M12 5v14M5 12h14",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  flow: "M5 6h5v4H5zM14 14h5v4h-5zM7.5 10v3a1 1 0 0 0 1 1H14",
  terminal: "M4 5h16v14H4zM7 9l3 3-3 3M12 15h5",
  screen: "M3 5h18v11H3zM8 20h8M12 16v4",
  play: "M8 5l11 7-11 7z",
  check: "M5 12l5 5L20 7",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  sliders: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  wifi: "M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 19.5h0",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  keyboard: "M3 6h18v12H3zM6 10h0M10 10h0M14 10h0M18 10h0M7 14h10",
  cpu: "M7 7h10v10H7zM10 10h4v4h-4zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4",
  brain: "M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V5a3 3 0 0 0-3-1zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1",
  agents: "M12 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM5 20a7 7 0 0 1 14 0",
  core: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  alert: "M12 3l10 18H2zM12 10v5M12 18h0",
  doc: "M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6",
  stop: "M7 7h10v10H7z",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
  folder: "M3 7h6l2 2h10v10H3z",
  database: "M12 4c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  chart: "M4 20V4M4 20h16M8 16l4-5 3 3 5-7",
  plug: "M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4",
};
export function icon(name, cls = "") {
  const d = P[name] || P.core;
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
}
const NAV_IC = { home: ["grid", "#38d4ff"], core: ["core", "#38d4ff"], agents: ["agents", "#19e6c1"], tasks: ["check", "#3dff9a"],
  calendar: ["calendar", "#5b8cff"], memory: ["brain", "#a77bff"], conversations: ["doc", "#38d4ff"], knowledge: ["database", "#ffd23f"],
  skills: ["sliders", "#ff9d2e"], workflows: ["flow", "#4f8bff"], security: ["shield", "#38d4ff"], trading: ["chart", "#3dff9a"],
  safety: ["stop", "#ff3b30"], settings: ["settings", "#7a8fa8"] };
export function mountNavSvg(nav) {
  if (!nav) return;
  nav.querySelectorAll("button[data-route]").forEach((b) => {
    if (b.querySelector(".nav-ic")) return;
    const [ic, col] = NAV_IC[b.dataset.route] || ["core", "#38d4ff"];
    const span = document.createElement("span");
    span.className = "nav-ic";
    span.style.setProperty("--nc", col);
    span.innerHTML = icon(ic);
    b.prepend(span);
  });
}
export function mountIcons(root = document) {
  root.querySelectorAll("i.ic[data-ic]").forEach((el) => {
    if (el.dataset.done) return;
    el.innerHTML = icon(el.dataset.ic);
    el.dataset.done = "1";
  });
}

export const esc = (v) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// ---- agents: distinct colour + wireframe shape per real role ----
export const AGENT_STYLE = {
  coding: { color: "#19e6c1", shape: "cube", label: "Coding" },
  research: { color: "#ff9d2e", shape: "icosa", label: "Research" },
  memory: { color: "#a77bff", shape: "pyramid", label: "Memory" },
  browser: { color: "#4f8bff", shape: "octa", label: "Browser" },
  task: { color: "#3dff9a", shape: "sphere", label: "Task" },
  system: { color: "#ff5a7a", shape: "prism", label: "System" },
  builder: { color: "#ffd23f", shape: "penta", label: "Builder" },
  video: { color: "#ff4fd8", shape: "tri", label: "Video" },
};
const styleOf = (id) => AGENT_STYLE[id] || { color: "#38d4ff", shape: "octa", label: id };

function shapeSvg(shape, r) {
  const L = (pts) => pts.map((p) => p.join(",")).join(" ");
  switch (shape) {
    case "cube": {
      const a = r * 0.72, o = r * 0.38;
      return `<rect x="${-a}" y="${-a + o / 2}" width="${a * 1.4}" height="${a * 1.4}"/><rect x="${-a + o}" y="${-a - o / 2}" width="${a * 1.4}" height="${a * 1.4}"/>
        <path d="M${-a} ${-a + o / 2}L${-a + o} ${-a - o / 2}M${a * .4} ${-a + o / 2}L${a * .4 + o} ${-a - o / 2}M${-a} ${a * .4 + o / 2 + a * 0}L${-a + o} ${a * .4 - o / 2}M${a * .4} ${a * .4 + o / 2}L${a * .4 + o} ${a * .4 - o / 2}"/>`;
    }
    case "pyramid":
      return `<polygon points="${L([[0, -r], [r, r * .7], [-r, r * .7]])}"/><path d="M0 ${-r}L${r * .25} ${r * .7}M0 ${-r}L${-r * .45} ${r * .35}L${r} ${r * .7}M${-r * .45} ${r * .35}L${-r} ${r * .7}"/>`;
    case "octa":
      return `<polygon points="${L([[0, -r], [r * .8, 0], [0, r], [-r * .8, 0]])}"/><path d="M${-r * .8} 0L${r * .8} 0M0 ${-r}L${r * .2} ${r * .15}L0 ${r}M${-r * .8} 0L${r * .2} ${r * .15}L${r * .8} 0"/>`;
    case "sphere":
      return `<circle r="${r}"/><ellipse rx="${r}" ry="${r * .35}"/><ellipse rx="${r * .35}" ry="${r}"/><ellipse rx="${r * .75}" ry="${r}"/>`;
    case "prism": {
      const pts = [...Array(6)].map((_, i) => [Math.cos(i * Math.PI / 3) * r, Math.sin(i * Math.PI / 3) * r]);
      return `<polygon points="${L(pts)}"/><path d="${pts.map((p) => `M0 0L${p[0]} ${p[1]}`).join("")}"/>`;
    }
    case "penta": {
      const pts = [...Array(5)].map((_, i) => [Math.cos(-Math.PI / 2 + i * 2 * Math.PI / 5) * r, Math.sin(-Math.PI / 2 + i * 2 * Math.PI / 5) * r]);
      const inner = pts.map((p) => [p[0] * .45, p[1] * .45]);
      return `<polygon points="${L(pts)}"/><polygon points="${L(inner)}"/><path d="${pts.map((p, i) => `M${p[0]} ${p[1]}L${inner[i][0]} ${inner[i][1]}`).join("")}"/>`;
    }
    case "tri":
      return `<polygon points="${L([[0, -r], [r * .9, r * .6], [-r * .9, r * .6]])}"/><polygon points="${L([[0, r * .9], [r * .9, -r * .4], [-r * .9, -r * .4]])}" opacity=".6"/>`;
    default: { // icosa
      const pts = [...Array(6)].map((_, i) => [Math.cos(Math.PI / 6 + i * Math.PI / 3) * r, Math.sin(Math.PI / 6 + i * Math.PI / 3) * r]);
      const tri = [[0, -r * .5], [r * .45, r * .3], [-r * .45, r * .3]];
      return `<polygon points="${L(pts)}"/><polygon points="${L(tri)}"/><path d="${pts.map((p, i) => { const t = tri[Math.floor(i / 2) % 3]; return `M${p[0]} ${p[1]}L${t[0]} ${t[1]}`; }).join("")}"/>`;
    }
  }
}
export function agentGlyph(id, size = 28) {
  const st = styleOf(id);
  const r = size * 0.36;
  return `<svg class="aglyph" viewBox="${-size / 2} ${-size / 2} ${size} ${size}" style="--ac:${st.color}"><g fill="none" stroke="${st.color}" stroke-width="1.3" stroke-linejoin="round">${shapeSvg(st.shape, r)}</g></svg>`;
}

const stateWord = (a) => {
  if (a.pending || String(a.detail || "").startsWith("needs_r3:")) return ["Needs you", "wait"];
  if (a.state === "active") return ["Active", "on"];
  if (a.state === "error") return ["Error", "err"];
  if (a.state === "done") return ["Done", "done"];
  return ["Standby", "off"];
};

// Home: compact 2x3 grid (Coding, Research, Memory, Browser, Task, System)
export function renderAgentsMini(el, agents, onPick) {
  if (!el) return;
  const want = ["coding", "research", "memory", "browser", "task", "system"];
  const rows = want.map((id) => (agents || []).find((a) => a.id === id)).filter(Boolean);
  el.innerHTML = rows.map((a) => {
    const [w, cls] = stateWord(a);
    const st = styleOf(a.id);
    return `<button class="am-card am-${cls}" data-mini="${esc(a.id)}" style="--ac:${st.color}" title="${esc(a.goal || a.detail || a.name)}">
      <span class="am-tile">${agentGlyph(a.id, 30)}</span>
      <span class="am-txt"><b>${esc(st.label)}</b><small><i class="dot"></i>${w}</small></span>
      <span class="am-wave"><i></i><i></i><i></i><i></i><i></i></span></button>`;
  }).join("") || `<div class="muted small">Agents not loaded yet.</div>`;
  el.querySelectorAll("[data-mini]").forEach((b) => { b.onclick = () => onPick && onPick(b.dataset.mini); });
}

// ---- Live feed: audit lines -> icon, title, subtitle, time ----
const FEED_KIND = [
  [/emergency_stop|halt/i, "stop", "red", "Emergency STOP"],
  [/resume_refused/i, "alert", "amber", "Resume refused"],
  [/resume/i, "play", "cyan", "Resumed"],
  [/error|fail/i, "alert", "red", null],
  [/needs_approval|r3|confirm/i, "alert", "amber", null],
  [/agent_done|done|write_brief/i, "check", "green", null],
  [/agent_start|start/i, "play", "blue", null],
  [/progress/i, "cpu", "blue", null],
  [/setting|policy|key|secret/i, "settings", "purple", null],
];
const nice = (s) => String(s || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export function feedView(it) {
  const action = String(it.action || "");
  const task = String(it.task || "");
  const text = action + " " + task;
  let kind = null;
  for (const src of [action, text]) {          // the action decides first; the task name only as a fallback
    for (const [re, ic, col, title] of FEED_KIND) if (re.test(src)) { kind = [ic, col, title]; break; }
    if (kind) break;
  }
  kind = kind || ["doc", "cyan", null];
  const title = kind[2] || (action ? nice(action) : (it.msg || it.detail || "Event"));
  const sub = [task && task !== action ? nice(task) : "", it.result || it.detail || it.msg || it.raw || ""].filter(Boolean).join(" · ");
  return { icon: kind[0], color: kind[1], title, sub, time: it.time || it.ts_ist || it.ts_utc || it.t || "" };
}

export function isToday(ts) {
  const m = /^(\d{4})-(\d\d)-(\d\d)/.exec(String(ts || ""));
  if (!m) return false;
  const d = new Date();
  return Number(m[1]) === d.getFullYear() && Number(m[2]) === d.getMonth() + 1 && Number(m[3]) === d.getDate();
}

// Mission timeline: today's agent + routine events from the audit log (real), newest last.
export function renderMission(el, items, shortTime) {
  if (!el) return;
  const rows = (items || []).filter((it) => isToday(it.time || it.ts_ist) && /agent_(start|done|error|needs_approval)|write_brief|emergency_stop|resume|workday|session/i.test(String(it.action || "")))
    .slice(-8);
  el.innerHTML = rows.length ? rows.map((it) => {
    const v = feedView(it);
    const a = String(it.action || "");
    const status = /resume_refused/.test(a) ? ["Refused", "warn"] : /resume/.test(a) ? ["Resumed", "ok"] : /done|write_brief/.test(a) ? ["Done", "ok"] : /error/.test(a) ? ["Error", "bad"] : /emergency_stop/.test(a) ? ["Stopped", "bad"] : /needs/.test(a) ? ["Waiting", "warn"] : ["Started", "info"];
    return `<div class="ms-row"><span class="ms-dot c-${v.color}"></span><span class="ms-t">${esc(shortTime(v.time))}</span><span class="ms-x"><b>${esc(v.title)}</b><small>${esc(v.sub.slice(0, 90))}</small></span><span class="ms-st ${status[1]}">${status[0]}</span></div>`;
  }).join("") : `<div class="muted small">Nothing logged today yet. Agent runs, briefs and STOP events appear here as they happen.</div>`;
}

// ---- System monitor rings ----
const CIRC = 2 * Math.PI * 26;
export function setRing(id, pct) {
  const el = document.getElementById(id);
  if (!el) return;
  const p = Math.max(0, Math.min(100, Number(pct) || 0));
  el.style.strokeDasharray = `${(p / 100) * CIRC} ${CIRC}`;
}
export function fmtRate(bps) {
  if (bps == null || !isFinite(bps)) return "—";
  if (bps >= 1048576) return `${(bps / 1048576).toFixed(1)} MB/s`;
  if (bps >= 1024) return `${Math.round(bps / 1024)} KB/s`;
  return `${Math.round(bps)} B/s`;
}
export function fmtUptime(s) {
  s = Math.max(0, Math.round(Number(s) || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
}
export function fmtBytes(n) {
  n = Number(n) || 0;
  if (n >= 1073741824) return `${(n / 1073741824).toFixed(1)} GB`;
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}
export function spark(svg, values) {
  if (!svg) return;
  const pl = svg.querySelector("polyline");
  const n = values.length;
  if (!pl || n < 2) return;
  pl.setAttribute("points", values.map((v, i) => `${(i / (n - 1)) * 120},${23 - (Math.max(0, Math.min(100, v)) / 100) * 22}`).join(" "));
}

// ---- LLM status rows ----
const LOGO = { gemini: ["G", "#4f8bff"], openai: ["◎", "#e8f6ff"], groq: ["q", "#ff7a3d"], anthropic: ["A", "#d9a77b"], ollama: ["🦙", "#cfd8e3"] };
const LLM_STATE = {
  connected: ["Connected", "ok"], missing_key: ["No key", "off"], auth_error: ["Key rejected / no credit", "bad"],
  network_error: ["Unreachable", "warn"], ready: ["Ready", "ok"], no_models: ["Installed · no models", "warn"],
  not_running: ["Installed · not running", "warn"], not_installed: ["Not installed", "off"],
};
export function renderLlmRows(el, providers, local) {
  if (!el) return;
  const rows = (providers || []).filter((p) => !(p.id === "anthropic" && p.state === "missing_key")).map((p) => ({ id: String(p.id || p.name).toLowerCase(), name: p.name, state: p.state }));
  if (local && local.ollama && !rows.some((r) => r.id === "ollama")) {
    rows.push({ id: "ollama", name: "Ollama (local)", state: local.ollama.state, extra: (local.ollama.models || []).length ? `${local.ollama.models.length} model(s)` : "" });
  }
  el.innerHTML = rows.map((r) => {
    const [lg, col] = LOGO[r.id] || [String(r.name || "?")[0], "#38d4ff"];
    const [w, cls] = LLM_STATE[r.state] || [r.state, "off"];
    return `<div class="llm-row"><span class="llm-logo" style="--lc:${col}">${esc(lg)}</span><span class="llm-name">${esc(r.name)}</span><span class="llm-st ${cls}"><i class="dot"></i>${esc(w)}${r.extra ? " · " + esc(r.extra) : ""}</span></div>`;
  }).join("") || `<div class="muted">No providers configured.</div>`;
}

// ---- Agents page: neon network diagram (core <-> agents), real states ----
export function renderNetDiagram(svg, agents, provider) {
  if (!svg) return;
  const list = agents || [];
  const cx = 500, cy = 200, rx = 400, ry = 150;
  const n = Math.max(1, list.length);
  let lines = "", nodes = "";
  list.forEach((a, i) => {
    const ang = -Math.PI / 2 + (i / n) * Math.PI * 2 + Math.PI / n;
    const x = cx + Math.cos(ang) * rx, y = cy + Math.sin(ang) * ry;
    const st = styleOf(a.id);
    const [w, cls] = stateWord(a);
    const mx = (cx + x) / 2, my = (cy + y) / 2 - 30;
    const d = `M${cx} ${cy} Q${mx} ${my} ${x.toFixed(1)} ${y.toFixed(1)}`;
    const dr = `M${x.toFixed(1)} ${y.toFixed(1)} Q${mx} ${my + 14} ${cx} ${cy}`;
    lines += `<path class="nd-link nd-${cls}" d="${d}" stroke="${st.color}"/><path class="nd-flow-out nd-${cls}" d="${d}" stroke="${st.color}"/><path class="nd-flow-in nd-${cls}" d="${dr}" stroke="${st.color}"/>`;
    nodes += `<g class="nd-agent nd-${cls}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})" data-agent-node="${esc(a.id)}" style="--ac:${st.color}">
      <circle class="nd-halo" r="34" fill="${st.color}"/>
      <g fill="none" stroke="${st.color}" stroke-width="1.6" stroke-linejoin="round" class="nd-shape">${shapeSvg(st.shape, 24)}</g>
      <text y="48" class="nd-name">${esc(st.label)}</text><text y="63" class="nd-state">${esc(w)}</text></g>`;
  });
  const chip = `<g class="nd-core" transform="translate(${cx} ${cy})">
    <rect x="-92" y="-48" width="184" height="96" rx="10"/><rect x="-80" y="-36" width="160" height="72" rx="6" class="nd-core-in"/>
    ${[...Array(7)].map((_, i) => `<path d="M${-60 + i * 20} -48v-10M${-60 + i * 20} 48v10"/>`).join("")}
    <text y="-8" class="nd-core-t">CENTRAL LLM</text><text y="10" class="nd-core-t">ADAPTER LAYER</text>
    <text y="28" class="nd-core-s">${esc(provider ? "via " + provider : "no provider connected")}</text></g>`;
  svg.innerHTML = `<defs><filter id="ndglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
    <g class="nd-lines">${lines}</g>${chip}<g filter="url(#ndglow)">${nodes}</g>`;
}

export function renderSources(el, sources) {
  if (!el) return;
  const IC = { web_search: "globe", memory: "brain", files: "folder", mcp: "plug", market_data: "chart" };
  const W = { connected: "Connected", empty: "Empty", not_connected: "Not connected", unavailable: "Unavailable" };
  el.innerHTML = (sources || []).map((s) => `<div class="nd-src s-${esc(s.state)}" title="${esc(s.detail)}">${icon(IC[s.id] || "database")}<span><b>${esc(s.label)}</b><small>${esc(W[s.state] || s.state)}</small></span></div>`).join("")
    || `<div class="muted small">Sources unavailable.</div>`;
}

// ---- Memory page: brain linked to real files and folders ----
export function renderMemoryMap(svg, mem) {
  if (!svg) return;
  const files = (mem?.recent || []).slice(0, 5);
  const folders = Object.entries(mem?.by_source || {});
  const cx = 500, cy = 230;
  let out = `<defs><filter id="mmglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
  const link = (x, y, col) => `<path class="mm-link" d="M${cx} ${cy} C${(cx + x) / 2} ${cy - 60}, ${(cx + x) / 2} ${y + 40}, ${x} ${y}" stroke="${col}"/>`;
  let cards = "";
  files.forEach((f, i) => {
    const y = 60 + i * (340 / Math.max(1, files.length - 1 || 1));
    const x = 190;
    out += link(x + 70, y, "#5fb8ff");
    cards += `<g class="mm-card" transform="translate(${x - 70} ${y - 18})"><rect width="160" height="36" rx="7"/><path class="mm-doc" d="M12 9h10l5 5v13H12z"/><text x="36" y="23">${esc(f.length > 18 ? f.slice(0, 17) + "…" : f)}</text></g>`;
  });
  folders.forEach(([name, n], i) => {
    const y = 60 + i * (340 / Math.max(1, folders.length - 1 || 1));
    const x = 820;
    out += link(x - 70, y, "#b48bff");
    cards += `<g class="mm-folder" transform="translate(${x - 80} ${y - 20})"><rect width="170" height="40" rx="8"/><path class="mm-fold" d="M12 12h8l3 3h13v14H12z"/><text x="46" y="19">${esc(nice(name.replace(/\.md$/, "")))}</text><text x="46" y="32" class="mm-n">${n} file${n === 1 ? "" : "s"}</text></g>`;
  });
  out += cards;
  out += `<g filter="url(#mmglow)" class="mm-brain"><use href="#brain-art" x="${cx - 130}" y="${cy - 105}" width="260" height="210"/></g>`;
  out += `<text x="${cx}" y="${cy + 128}" class="mm-cap">${mem?.nodes ?? 0} memory files · ${fmtBytes(mem?.bytes)}</text>`;
  if (!files.length && !folders.length) out += `<text x="${cx}" y="40" class="mm-cap">No memory files yet — STATE.md, journal, memory, notes and reports are indexed when present.</text>`;
  svg.innerHTML = out;
}

// ---- Security page: AI shield bound to real checks ----
export function renderShield(svg, el, d, policyOk) {
  if (!svg || !d) return;
  const a = d.audit || {}, k = d.secrets || {}, h = d.halt || {};
  const checks = [
    { id: "integrity", label: "Data Integrity", ok: !!a.ok, val: a.ok ? `Audit chain intact · ${a.chained} chained` : "Audit chain FAILED" },
    { id: "stop", label: "Emergency STOP", ok: true, val: h.stopped ? "HALTED — standby" : `Armed · hotkey ${h.hotkey?.state || "?"}`, warn: !!h.stopped },
    { id: "vault", label: "Key Vault", ok: !!k.credential_manager && !k.plaintext_in_file, val: k.credential_manager ? `${k.in_credential_manager} key(s) in Credential Manager · ${k.plaintext_in_file} plain-text` : "Credential Manager unavailable" },
    { id: "policy", label: "Access Policy R1–R4", ok: policyOk !== false, val: `${(d.levels || []).length} levels · unknown actions = R4` },
  ];
  const allOk = checks.every((c) => c.ok);
  const pos = [[180, 110], [820, 110], [180, 330], [820, 330]];
  let s = `<defs><linearGradient id="shg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3fb6ff" stop-opacity=".55"/><stop offset="1" stop-color="#0a2a5a" stop-opacity=".15"/></linearGradient>
    <filter id="shglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;
  // network nodes (decorative grid) behind
  for (let i = 0; i < 26; i++) {
    const x = 60 + ((i * 137) % 880), y = 30 + ((i * 89) % 380);
    s += `<circle cx="${x}" cy="${y}" r="2" class="sh-node"/>`;
    if (i) { const px = 60 + (((i - 1) * 137) % 880), py = 30 + (((i - 1) * 89) % 380); s += `<line x1="${px}" y1="${py}" x2="${x}" y2="${y}" class="sh-net"/>`; }
  }
  checks.forEach((c, i) => {
    const [x, y] = pos[i];
    const tone = !c.ok ? "bad" : (c.warn ? "warn" : "ok");
    s += `<line x1="${x < 500 ? x + 120 : x - 120}" y1="${y}" x2="${x < 500 ? 400 : 600}" y2="${y < 220 ? 170 : 270}" class="sh-wire ${tone}"/>
      <g class="sh-label ${tone}" transform="translate(${x - 120} ${y - 28})"><rect width="240" height="56" rx="10"/><text x="14" y="22" class="sh-l">${esc(c.label)}</text><text x="14" y="41" class="sh-v">${esc(c.val)}</text><circle cx="222" cy="18" r="5"/></g>`;
  });
  s += `<g class="sh-shield ${allOk ? "ok" : "bad"}" filter="url(#shglow)" transform="translate(500 215)">
    <path d="M0 -150 L120 -105 V-10 C120 75 60 125 0 150 C-60 125 -120 75 -120 -10 V-105 Z" fill="url(#shg)"/>
    <path d="M0 -122 L96 -86 V-8 C96 60 48 101 0 122 C-48 101 -96 60 -96 -8 V-86 Z" class="sh-in"/>
    <path d="M-40 0 L-10 30 L45 -30" class="sh-tick"/></g>
    <text x="500" y="408" class="sh-title ${allOk ? "ok" : "bad"}">${allOk ? "AI SHIELD ACTIVE" : "AI SHIELD — ATTENTION"}</text>`;
  svg.innerHTML = s;
  if (el) el.innerHTML = checks.map((c) => `<div class="sec-card ${!c.ok ? "bad" : (c.warn ? "warn" : "ok")}"><b>${esc(c.label)}</b><div>${esc(c.val)}</div></div>`).join("") +
    `<div class="sec-card"><b>Not monitored by Jarvis</b><div class="muted">Firewall and antivirus are Windows' job; Jarvis does not read or change them.</div></div>`;
}

// ---- Trading page: layouts only; honest empty states until a data source is connected ----
const DASH = "—";
const emptyNote = (what) => `<div class="tr-empty">${icon("plug")}<span>Connect a data source to see ${esc(what)}.</span></div>`;
function table(cols, rows) {
  return `<table class="tr-tab"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? "" : ' class="k"'}>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function gauge(label) {
  return `<div class="tr-gauge"><svg viewBox="0 0 120 70"><path d="M10 62 A50 50 0 0 1 110 62" class="g-trk"/><path d="M10 62 A50 50 0 0 1 43 15" class="g-bear"/><path d="M77 15 A50 50 0 0 1 110 62" class="g-bull"/></svg><b>${DASH}</b><small>${esc(label)}</small><div class="g-lbl"><span>Bearish</span><span>Bullish</span></div></div>`;
}
export function renderTrading(el) {
  if (!el || el.dataset.built) return;
  el.dataset.built = "1";
  const tf = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"].map((t) => `<button disabled>${t}</button>`).join("");
  const osc = ["RSI (14)", "MACD (12,26,9)", "Stoch %K (14,3,3)", "CCI (20)", "ADX (14)", "Williams %R (14)", "Momentum (10)"].map((n) => [n, DASH, DASH, DASH]);
  const ma = ["EMA 10", "EMA 20", "EMA 50", "SMA 200"].map((n) => [n, DASH, DASH, DASH]);
  const piv = ["R3", "R2", "R1", "Pivot", "S1", "S2", "S3"].map((n) => [n, DASH, DASH, DASH, DASH, DASH]);
  el.innerHTML = `
  <div class="panel tr-p tr-stat"><h3>Statistical Validation <span class="h3-sub">walk-forward</span></h3>
    <svg viewBox="0 0 600 120" class="tr-chart" preserveAspectRatio="none">${[0, 1, 2, 3, 4, 5].map((i) => `<rect x="${i * 100}" y="0" width="70" height="120" class="trn"/><rect x="${i * 100 + 70}" y="0" width="30" height="120" class="oos"/>`).join("")}<line x1="0" y1="119" x2="600" y2="119" class="ax"/></svg>
    <div class="tr-legend"><span class="trn-l">Training</span><span class="oos-l">Out-of-sample</span></div>
    <div class="tr-metrics"><div><small>Sharpe</small><b>${DASH}</b><i>95% CI ${DASH}</i></div><div><small>p-value</small><b>${DASH}</b><i>vs random</i></div><div><small>Return dist.</small><b>${DASH}</b><i>vs benchmark</i></div><div><small>Monte Carlo</small><b>${DASH}</b><i>5 / 50 / 75 / 95th pct</i></div></div>
    ${emptyNote("walk-forward equity, Sharpe and Monte Carlo results")}</div>
  <div class="panel tr-p tr-ta"><h3>Technical Analysis</h3>
    <div class="tr-tf">${tf}</div>
    <div class="tr-gauges">${gauge("Oscillators")}${gauge("Summary")}${gauge("Moving Averages")}</div>
    <div class="tr-two">${table(["Oscillator", "Value", "Signal", "Strength"], osc)}${table(["Moving avg", "Value", "Signal", "Strength"], ma)}</div>
    ${table(["Pivot", "Classic", "Fibonacci", "Camarilla", "Woodie", "DeMark"], piv)}
    ${emptyNote("indicator values and signals")}</div>
  <div class="panel tr-p"><h3>Order Book Depth</h3>
    <div class="tr-two">${table(["Bid qty", "Bid"], [...Array(5)].map(() => [DASH, DASH]))}${table(["Ask", "Ask qty"], [...Array(5)].map(() => [DASH, DASH]))}</div>
    <div class="tr-spread">Best bid ${DASH} · Best ask ${DASH} · Spread ${DASH}</div>${emptyNote("live bid/ask depth")}</div>
  <div class="panel tr-p"><h3>News Sentiment</h3>
    <div class="tr-sent"><svg viewBox="0 0 42 42" class="tr-donut"><circle cx="21" cy="21" r="15.9" class="g-trk"/></svg>
      <div><div>Ticker <b>${DASH}</b> · Bias <b>${DASH}</b></div><div class="tr-cnt"><span class="pos">Positive ${DASH}</span><span class="neu">Neutral ${DASH}</span><span class="neg">Negative ${DASH}</span></div></div></div>
    ${emptyNote("articles with AI summaries")}</div>
  <div class="panel tr-p"><h3>Portfolio Risk <span class="h3-sub">paper</span></h3>
    <div class="tr-metrics"><div><small>VaR 95%</small><b>${DASH}</b></div><div><small>CVaR 95%</small><b>${DASH}</b></div><div><small>Sectors</small><b>${DASH}</b></div></div>
    ${table(["Stress scenario", "Impact"], [["Market −10%", DASH], ["Rates +100 bp", DASH], ["INR −5%", DASH]])}
    ${table(["Holding", "Qty", "Weight", "P&L"], [["No paper portfolio yet", "", "", ""]])}</div>
  <div class="panel tr-p"><h3>Markov Regime <span class="h3-sub">transition matrix</span></h3>
    ${table(["From \\ To", "Bull", "Bear", "Side"], [["Bull", DASH, DASH, DASH], ["Bear", DASH, DASH, DASH], ["Side", DASH, DASH, DASH]])}
    <div class="tr-candles"></div>${emptyNote("price history and regime estimates")}</div>`;
}
