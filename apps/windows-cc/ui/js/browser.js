// apps/windows-cc/ui/js/browser.js — Browser tab: live view of Jarvis's Edge window (Phase 3c).
import { call } from "./bridge.js";
import { esc } from "./v3.js";

const $ = (id) => document.getElementById(id);
let mounted = false, timer = 0, busy = false, shot = { w: 0, h: 0 }, ticks = 0;

function active() { return $("page-browser") && $("page-browser").classList.contains("active"); }

function msg(t, kind = "") { const m = $("br-msg"); if (m) { m.textContent = t || ""; m.className = `small ${kind === "err" ? "tr-err" : "muted"}`; } }

function renderTabs(tabs) {
  const el = $("br-tabs");
  if (!el) return;
  el.innerHTML = (tabs || []).map((t) => `<button class="br-tab${t.active ? " on" : ""}" data-tab="${esc(t.id)}" title="${esc(t.url)}">
      <span>${esc(t.title || t.url || "New tab")}</span><i data-close="${esc(t.id)}" title="Close tab">×</i></button>`).join("")
    + `<button class="br-tab add" data-newtab="1" title="New tab">+</button>`;
}

function renderInfo(d) {
  if (!d) return;
  if (d.url !== undefined && document.activeElement !== $("br-url")) $("br-url").value = d.url || "";
  if (d.tabs) renderTabs(d.tabs);
  if (d.blocked) msg(d.blocked, "err");
}

async function refreshStatus() {
  const r = await call("browser_status");
  if (!r.ok) { msg(r.error, "err"); return null; }
  const s = r.data;
  $("br-state").innerHTML = s.halted ? `<span class="tr-err">STOPPED — automation blocked</span>`
    : s.running ? `<span class="pos">running</span> · ${esc(s.browser)} · profile <code>browser-profile</code> (logins persist)`
    : `<span class="muted">not running</span> · ${esc(s.browser)}`;
  $("br-start").hidden = s.running;
  renderTabs(s.tabs);
  const a = (s.tabs || []).find((t) => t.active);
  if (a && document.activeElement !== $("br-url")) $("br-url").value = a.url;
  return s;
}

async function snap() {
  if (busy || !active()) return;
  busy = true;
  try {
    const r = await call("browser_shot");
    if (r.ok) {
      $("br-view").src = `data:image/jpeg;base64,${r.data.jpeg_b64}`;
      shot = { w: r.data.css_w || 0, h: r.data.css_h || 0 };
      $("br-empty").hidden = true;
      if (/capture|not running/i.test($("br-msg").textContent)) msg("");
      if (document.activeElement !== $("br-url")) $("br-url").value = r.data.url || "";
    } else if (r.halted) {
      $("br-state").innerHTML = `<span class="tr-err">STOPPED — automation blocked</span>`;
    } else if (/not running|no open tab/.test(r.error || "")) {
      $("br-empty").hidden = false;
    } else if (r.error) { msg(r.error, "err"); }
  } finally { busy = false; }
}

function loop() {
  clearInterval(timer);
  timer = setInterval(() => { if (!active()) return; snap(); if (++ticks % 4 === 0) refreshStatus(); }, 1500);
}

async function act(fn, ...args) {
  msg("…");
  const r = await call(fn, ...args);
  if (!r.ok) { msg(r.error || "failed", "err"); return r; }
  msg("");
  renderInfo(r.data && r.data.data ? r.data.data : r.data);
  snap();
  return r;
}

export function renderBrowser(host) {
  if (!host) return;
  if (!mounted) {
    mounted = true;
    host.innerHTML = `
      <div class="panel br-bar">
        <div class="br-row">
          <button class="set-btn" data-nav="-1" title="Back">◀</button>
          <button class="set-btn" data-nav="1" title="Forward">▶</button>
          <button class="set-btn" data-nav="0" title="Reload">⟳</button>
          <input id="br-url" class="br-url" placeholder="Search Google or type a URL" autocomplete="off" spellcheck="false" />
          <button class="set-btn" id="br-go">Go</button>
          <button class="set-btn" id="br-start">Open browser</button>
        </div>
        <div id="br-tabs" class="br-tabs"></div>
        <div class="small muted"><span id="br-state">…</span></div>
        <div id="br-msg" class="small muted"></div>
      </div>
      <div class="br-grid">
        <div class="panel br-viewport">
          <div id="br-empty" class="br-empty muted">Press <b>Open browser</b> (or type a site above). Jarvis opens Microsoft Edge with its own profile — sign in there yourself; logins stay after restart.</div>
          <img id="br-view" alt="Live view of Jarvis browser" />
          <div class="br-type">
            <input id="br-text" placeholder="Type into the focused field on the page (not passwords — use the Edge window)" autocomplete="off" />
            <button class="set-btn" id="br-send">Type</button><button class="set-btn" id="br-enter">Type + Enter</button>
          </div>
        </div>
        <div class="panel br-side">
          <h3>Ask Jarvis about this page</h3>
          <textarea id="br-q" rows="3" placeholder="e.g. Summarise this page · What are the key numbers? · Compare these results"></textarea>
          <div class="br-row"><button class="set-btn" id="br-ask">Ask Jarvis</button><button class="set-btn" id="br-sum">Summarise</button><button class="set-btn" id="br-read">Read text</button></div>
          <div id="br-answer" class="br-answer small"></div>
          <p class="small muted">Click the live view to click the page, scroll it with the wheel. Jarvis never types passwords, OTPs or card numbers, needs your approval (R3) before buying/sending/posting, and won't automate banking, broker or patient sites. Emergency STOP blocks all browser automation.</p>
        </div>
      </div>`;
    host.addEventListener("click", onClick);
    $("br-url").addEventListener("keydown", (e) => { if (e.key === "Enter") act("browser_open", $("br-url").value, false); });
    $("br-text").addEventListener("keydown", (e) => { if (e.key === "Enter") { act("browser_user_text", $("br-text").value, true); $("br-text").value = ""; } });
    $("br-view").addEventListener("click", (e) => {
      const img = e.currentTarget, r = img.getBoundingClientRect();
      if (!shot.w || !r.width) return;
      act("browser_user_click", (e.clientX - r.left) * shot.w / r.width, (e.clientY - r.top) * shot.h / r.height);
    });
    $("br-view").addEventListener("wheel", (e) => { e.preventDefault(); call("browser_scroll", Math.round(e.deltaY * 1.5)).then(snap); }, { passive: false });
    loop();
  }
  refreshStatus().then((s) => { if (s && s.running) snap(); else $("br-empty").hidden = false; });
}

async function ask(q) {
  $("br-answer").innerHTML = `<span class="muted">Reading the page and thinking…</span>`;
  const r = await call("browser_ask", q);
  if (!r.ok) { $("br-answer").innerHTML = `<span class="tr-err">${esc(r.error)}</span>`; return; }
  const d = r.data;
  $("br-answer").innerHTML = `<div class="muted">${esc(d.title || "")} · via ${esc(d.provider)}</div><div class="br-md">${esc(d.answer).replace(/\n/g, "<br>")}</div>`;
}

async function onClick(e) {
  const b = e.target.closest("button, i[data-close]");
  if (!b) return;
  if (b.dataset.close) { e.stopPropagation(); await act("browser_close_tab", b.dataset.close); refreshStatus(); return; }
  if (b.dataset.tab) { await act("browser_activate", b.dataset.tab); return; }
  if (b.dataset.newtab) { await act("browser_open", "https://www.google.com/", true); return; }
  if (b.dataset.nav !== undefined) { await act("browser_nav", Number(b.dataset.nav)); return; }
  if (b.id === "br-go") await act("browser_open", $("br-url").value, false);
  else if (b.id === "br-start") { msg("Starting Edge…"); const r = await call("browser_start", $("br-url").value || "https://www.google.com/"); if (!r.ok) msg(r.error, "err"); else { msg(""); await refreshStatus(); snap(); } }
  else if (b.id === "br-send") { await act("browser_user_text", $("br-text").value, false); $("br-text").value = ""; }
  else if (b.id === "br-enter") { await act("browser_user_text", $("br-text").value, true); $("br-text").value = ""; }
  else if (b.id === "br-ask") ask($("br-q").value);
  else if (b.id === "br-sum") ask("");
  else if (b.id === "br-read") {
    const r = await call("browser_read");
    $("br-answer").innerHTML = r.ok ? `<div class="muted">${esc(r.data.title)} · ${(r.data.elements || []).length} interactive elements</div><pre class="task-report">${esc(r.data.text)}</pre>` : `<span class="tr-err">${esc(r.error)}</span>`;
  }
}
