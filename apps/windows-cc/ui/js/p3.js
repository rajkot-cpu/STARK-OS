// apps/windows-cc/ui/js/p3.js — Phase 3 pages: live Trading (real indicators, paper ledger, live gate),
// Tasks (Research → Analyst → Writer chain on the persistent queue), Memory search, Settings
// (keys & brokers, local AI, local API). Every number comes from the bridge; nothing is invented.
import { call } from "./bridge.js";
import { esc } from "./v3.js";

const DASH = "—";
const $ = (id) => document.getElementById(id);
const nf = (v, d = 2) => (v === null || v === undefined || !isFinite(v)) ? DASH : Number(v).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 2) => (v === null || v === undefined || !isFinite(v)) ? DASH : `${(v * 100).toFixed(d)}%`;
const istTime = (unix) => unix ? new Date(unix * 1000).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: true }) + " IST" : DASH;
const actCls = (a) => a === "BUY" || a === "STRONG BUY" ? "pos" : (a === "SELL" || a === "STRONG SELL" ? "neg" : "neu");

function table(cols, rows, cls = "") {
  return `<table class="tr-tab ${cls}"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? "" : ' class="k"'}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
function gauge(label, sum) {
  const s = sum ? Math.max(-1, Math.min(1, sum.score)) : 0;
  const ang = Math.PI * (1 - (s + 1) / 2);
  const x = 60 + 44 * Math.cos(ang), y = 62 - 44 * Math.sin(ang);
  return `<div class="tr-gauge"><svg viewBox="0 0 120 70"><path d="M10 62 A50 50 0 0 1 110 62" class="g-trk"/><path d="M10 62 A50 50 0 0 1 43 15" class="g-bear"/><path d="M77 15 A50 50 0 0 1 110 62" class="g-bull"/>${sum ? `<line x1="60" y1="62" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="g-needle"/>` : ""}</svg><b class="${sum ? actCls(sum.rating) : ""}">${sum ? esc(sum.rating) : DASH}</b><small>${esc(label)}${sum ? ` · ${sum.buy}↑ ${sum.neutral}· ${sum.sell}↓` : ""}</small><div class="g-lbl"><span>Bearish</span><span>Bullish</span></div></div>`;
}
function sparkPath(vals, w = 600, h = 70) {
  if (!vals || vals.length < 2) return "";
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  return vals.map((v, i) => `${i ? "L" : "M"}${(i / (vals.length - 1) * w).toFixed(1)} ${(h - 4 - (v - lo) / span * (h - 8)).toFixed(1)}`).join(" ");
}

// ---------------- Trading ----------------
const tr = { symbol: "NIFTY", tf: "1d", snap: null, busy: false, news: null };

export function renderTradingLive(el) {
  if (!el) return;
  if (!el.dataset.p3) {
    el.dataset.p3 = "1";
    el.innerHTML = `<div class="panel tr-p tr-head" id="tr-head"></div>
      <div class="panel tr-p tr-signal" id="tr-signal"></div>
      <div class="panel tr-p tr-ta" id="tr-ta"></div>
      <div class="panel tr-p" id="tr-stat"></div>
      <div class="panel tr-p" id="tr-paper"></div>
      <div class="panel tr-p" id="tr-regime"></div>
      <div class="panel tr-p" id="tr-news"></div>
      <div class="panel tr-p" id="tr-book"></div>
      <div class="panel tr-p" id="tr-live"></div>`;
    el.addEventListener("click", onTradingClick);
  }
  loadTrading();
  loadPaper();
  loadLive();
  if (!tr.news) renderNews();
}

async function loadTrading() {
  if (tr.busy) return;
  tr.busy = true;
  renderHead(true);
  const r = await call("trading_snapshot", tr.symbol, tr.tf);
  tr.busy = false;
  tr.snap = r;
  const src = $("tr-source");
  if (src) {
    src.textContent = r.ok ? `Market data: ${r.data.source}` : "Market data: not connected";
    src.classList.toggle("ok", !!r.ok);
  }
  renderHead(false);
  renderSignal();
  renderTA();
  renderStat();
  renderRegime();
  renderBook();
}

function renderHead(loading) {
  const el = $("tr-head");
  if (!el) return;
  const r = tr.snap;
  const syms = ["NIFTY", "BANKNIFTY"].map((s) => `<button class="tr-sym${s === tr.symbol ? " on" : ""}" data-sym="${s}">${s}</button>`).join("");
  const tfs = [["5m", "M5"], ["15m", "M15"], ["1h", "H1"], ["1d", "D1"], ["1wk", "W1"]].map(([v, l]) => `<button class="tr-tfb${v === tr.tf ? " on" : ""}" data-tf="${v}">${l}</button>`).join("");
  let price = `<span class="muted">${loading ? "Loading real market data…" : ""}</span>`;
  if (r && r.ok) {
    const d = r.data;
    price = `<span class="tr-last">${nf(d.last)}</span><span class="${d.change >= 0 ? "pos" : "neg"}">${d.change >= 0 ? "▲" : "▼"} ${nf(Math.abs(d.change))} (${d.change_pct.toFixed(2)}%)</span><span class="muted small">as of ${istTime(d.market_time)} · ${d.bars} bars · delayed</span>`;
  } else if (r && !loading) {
    price = `<span class="tr-err">Not connected: ${esc(r.error || "market data unavailable")}</span>`;
  }
  el.innerHTML = `<div class="tr-headrow"><div class="tr-syms">${syms}</div><div class="tr-tf">${tfs}</div><button class="set-btn" data-act="refresh">${loading ? "…" : "Refresh"}</button></div><div class="tr-price">${price}</div>
    ${r && r.ok ? `<svg viewBox="0 0 600 70" class="tr-spark" preserveAspectRatio="none"><path d="${sparkPath(r.data.spark)}"/></svg>` : ""}`;
}

function renderSignal() {
  const el = $("tr-signal");
  if (!el) return;
  const r = tr.snap;
  if (!r || !r.ok) { el.innerHTML = `<h3>Signal</h3><p class="muted small">No signal without market data.</p>`; return; }
  const s = r.data.signal;
  el.innerHTML = `<h3>Signal <span class="h3-sub">you decide · paper</span></h3>
    <div class="tr-sigrow"><b class="tr-rating ${actCls(s.rating)}">${esc(s.rating)}</b><span class="small muted">${esc(s.basis)} · ${s.buy} buy / ${s.neutral} neutral / ${s.sell} sell · score ${s.score.toFixed(2)}</span></div>
    <div class="tr-order"><label>Qty <input id="tr-qty" type="number" min="1" max="1000" value="1"/></label>
      <button class="set-btn buy" data-act="paper-buy">Paper BUY ${esc(tr.symbol)}</button>
      <button class="set-btn sell" data-act="paper-sell">Paper SELL</button></div>
    <p class="muted small">Jarvis only suggests. Nothing is bought until you press a button, and these buttons only write to the paper ledger (fills at the delayed last price). Not investment advice.</p>
    <div id="tr-order-msg" class="small"></div>`;
}

function renderTA() {
  const el = $("tr-ta");
  if (!el) return;
  const r = tr.snap;
  if (!r || !r.ok) { el.innerHTML = `<h3>Technical Analysis</h3><p class="muted small">Waiting for market data.</p>`; return; }
  const t = r.data.technicals;
  const osc = t.oscillators.map((o) => [esc(o.name), nf(o.value), `<span class="${actCls(o.action)}">${o.action}</span>`]);
  const ma = t.moving_averages.map((o) => [esc(o.name), nf(o.value), `<span class="${actCls(o.action)}">${o.action}</span>`]);
  const P = t.pivots, rows = ["R3", "R2", "R1", "P", "S1", "S2", "S3"].map((k) => [k === "P" ? "Pivot" : k, nf(P.classic[k]), nf(P.fibonacci[k]), nf(P.camarilla[k]), nf(P.woodie[k]), P.demark[k] !== undefined ? nf(P.demark[k]) : DASH]);
  el.innerHTML = `<h3>Technical Analysis <span class="h3-sub">${esc(tr.tf)} · ATR ${nf(t.atr)}</span></h3>
    <div class="tr-gauges">${gauge("Oscillators", t.summary.oscillators)}${gauge("Summary", t.summary.overall)}${gauge("Moving Averages", t.summary.moving_averages)}</div>
    <div class="tr-two">${table(["Oscillator", "Value", "Action"], osc)}${table(["Moving avg", "Value", "Action"], ma)}</div>
    ${table(["Pivot", "Classic", "Fibonacci", "Camarilla", "Woodie", "DeMark"], rows)}
    <p class="muted small">Pivots from the previous completed ${esc(tr.tf)} bar (${istTime(t.pivots_from)}).</p>`;
}

function renderStat() {
  const el = $("tr-stat");
  if (!el) return;
  const r = tr.snap;
  if (!r || !r.ok) { el.innerHTML = `<h3>Statistical Validation</h3><p class="muted small">Waiting for market data.</p>`; return; }
  const st = r.data.stats, mc = r.data.monte_carlo, wf = r.data.walk_forward;
  let bars = "";
  if (wf.ok) {
    const n = wf.folds.length, w = 600 / n, mx = Math.max(0.01, ...wf.folds.map((f) => Math.max(Math.abs(f.oos_return), Math.abs(f.buy_hold_return))));
    bars = wf.folds.map((f, i) => {
      const h1 = Math.abs(f.oos_return) / mx * 50, h2 = Math.abs(f.buy_hold_return) / mx * 50;
      return `<rect x="${i * w + 8}" y="${f.oos_return >= 0 ? 60 - h1 : 60}" width="${w / 2 - 10}" height="${h1}" class="oos"/><rect x="${i * w + w / 2}" y="${f.buy_hold_return >= 0 ? 60 - h2 : 60}" width="${w / 2 - 10}" height="${h2}" class="trn"/><text x="${i * w + w / 2}" y="118" class="lbl">F${f.fold} ${f.fast}/${f.slow}</text>`;
    }).join("");
  }
  el.innerHTML = `<h3>Statistical Validation <span class="h3-sub">daily · ${st.ok ? st.n : 0} returns</span></h3>
    ${wf.ok ? `<svg viewBox="0 0 600 122" class="tr-chart" preserveAspectRatio="none"><line x1="0" y1="60" x2="600" y2="60" class="ax"/>${bars}</svg>
    <div class="tr-legend"><span class="oos-l">Walk-forward OOS return (EMA cross)</span><span class="trn-l">Buy &amp; hold same window</span></div>` : `<p class="muted small">${esc(wf.error || "walk-forward unavailable")}</p>`}
    <div class="tr-metrics">
      <div><small>Sharpe (B&amp;H)</small><b>${st.ok ? st.sharpe.toFixed(2) : DASH}</b><i>95% CI ${st.ok ? `${st.sharpe_ci95[0].toFixed(2)} … ${st.sharpe_ci95[1].toFixed(2)}` : DASH}</i></div>
      <div><small>p-value</small><b>${st.ok ? st.p_value.toFixed(3) : DASH}</b><i>mean return ≠ 0</i></div>
      <div><small>OOS Sharpe</small><b>${wf.ok ? wf.oos_sharpe.toFixed(2) : DASH}</b><i>OOS return ${wf.ok ? pct(wf.oos_return, 1) : DASH}</i></div>
      <div><small>Monte Carlo 20d</small><b>${mc.ok ? pct(mc.prob_up, 0) : DASH}</b><i>${mc.ok ? `5/50/95%: ${nf(mc.p5, 0)} / ${nf(mc.p50, 0)} / ${nf(mc.p95, 0)}` : DASH}</i></div>
      <div><small>Max drawdown</small><b>${st.ok ? pct(st.max_drawdown, 1) : DASH}</b><i>vol ${st.ok ? pct(st.vol_annual, 1) : DASH} / yr</i></div>
    </div><p class="muted small">Descriptive statistics of past data (bootstrap, seeded). Not a forecast.</p>`;
}

function renderRegime() {
  const el = $("tr-regime");
  if (!el) return;
  const r = tr.snap;
  if (!r || !r.ok || !r.data.regime.ok) { el.innerHTML = `<h3>Markov Regime</h3><p class="muted small">${esc(r && r.ok ? r.data.regime.error : "Waiting for market data.")}</p>`; return; }
  const g = r.data.regime, N = g.states;
  const rows = N.map((from, i) => [from, ...g.matrix[i].map((p, j) => `<span class="${i === N.indexOf(g.current) ? "hl" : ""}">${(p * 100).toFixed(0)}%</span>`)]);
  el.innerHTML = `<h3>Markov Regime <span class="h3-sub">daily returns · band ±${(g.band * 100).toFixed(2)}%</span></h3>
    <div class="tr-sigrow"><span>Today: <b>${esc(g.current)}</b></span><span>Trend (SMA20 vs 50): <b>${esc(g.trend)}</b></span></div>
    ${table(["From \\ To", ...N], rows)}
    <p class="muted small">Next-day odds from ${esc(g.current)}: ${N.map((n) => `${n} ${(g.next[n] * 100).toFixed(0)}%`).join(" · ")}. Occupancy: ${N.map((n) => `${n} ${(g.occupancy[n] * 100).toFixed(0)}%`).join(" · ")}.</p>`;
}

function renderBook() {
  const el = $("tr-book");
  if (!el) return;
  const reason = tr.snap && tr.snap.ok ? tr.snap.data.order_book.reason : "No market data.";
  el.innerHTML = `<h3>Order Book Depth</h3><div class="tr-empty"><span>Not available — ${esc(reason)} It appears here once a broker data adapter is connected.</span></div>`;
}

function renderNews() {
  const el = $("tr-news");
  if (!el) return;
  const n = tr.news;
  let body = `<p class="muted small">Fetches real headlines (DuckDuckGo News, no key) and classifies them with the local AI model first.</p>`;
  if (n === "loading") body = `<p class="muted small">Reading headlines and classifying… (local model on CPU can take ~30 s)</p>`;
  else if (n && !n.ok) body = `<p class="tr-err small">${esc(n.error)}</p>`;
  else if (n && n.ok) {
    const c = n.data.counts;
    body = `<div class="tr-cnt"><span class="pos">Positive ${c.positive}</span><span class="neu">Neutral ${c.neutral}</span><span class="neg">Negative ${c.negative}</span>${c.unclassified ? `<span class="muted">Unclassified ${c.unclassified}</span>` : ""}<span class="muted">by ${esc(n.data.provider || "—")}</span></div>
      <ul class="tr-news-l">${n.data.items.map((it) => `<li><span class="${it.label === "positive" ? "pos" : it.label === "negative" ? "neg" : "neu"}">●</span> ${esc(it.title)} <span class="muted">${esc(it.source)}</span></li>`).join("")}</ul>`;
  }
  el.innerHTML = `<h3>News Sentiment <span class="h3-sub">${esc(tr.symbol)}</span></h3>${body}<button class="set-btn" data-act="news">${n && n !== "loading" ? "Re-analyse" : "Analyse headlines"}</button>`;
}

async function loadPaper() {
  const el = $("tr-paper");
  if (!el) return;
  const r = await call("paper_summary");
  if (!r.ok) { el.innerHTML = `<h3>Paper Portfolio</h3><p class="tr-err small">${esc(r.error)}</p>`; return; }
  const d = r.data;
  const st = tr.snap && tr.snap.ok ? tr.snap.data.stats : null;
  const var95 = st && st.ok ? st.var95 * d.market_value : null, cvar = st && st.ok ? st.cvar95 * d.market_value : null;
  const pos = d.positions.length ? d.positions.map((p) => [esc(p.symbol), nf(p.qty, 0), nf(p.avg), nf(p.mark), `<span class="${(p.unrealized || 0) >= 0 ? "pos" : "neg"}">${nf(p.unrealized)}</span>`]) : [["No paper positions yet", "", "", "", ""]];
  const ords = d.orders.slice(0, 6).map((o) => [esc(o.ts.slice(5, 16).replace("T", " ")), `<span class="${o.side === "BUY" ? "pos" : "neg"}">${o.side}</span>`, `${nf(o.qty, 0)} ${esc(o.symbol)}`, nf(o.price), esc(o.origin)]);
  el.innerHTML = `<h3>Paper Portfolio <span class="h3-sub">virtual ₹${nf(d.start_cash, 0)}</span></h3>
    <div class="tr-metrics"><div><small>Equity</small><b>₹${nf(d.equity, 0)}</b></div><div><small>Cash</small><b>₹${nf(d.cash, 0)}</b></div>
      <div><small>Unrealised</small><b class="${d.unrealized >= 0 ? "pos" : "neg"}">${nf(d.unrealized, 0)}</b></div><div><small>Realised</small><b>${nf(d.realized, 0)}</b></div>
      <div><small>VaR 95% (1d)</small><b>${var95 ? "₹" + nf(var95, 0) : DASH}</b><i>CVaR ${cvar ? "₹" + nf(cvar, 0) : DASH}</i></div></div>
    ${table(["Holding", "Qty", "Avg", "Mark", "P&L"], pos)}
    ${ords.length ? table(["Time (IST)", "Side", "Qty", "Price", "Origin"], ords) : ""}
    <button class="set-btn" data-act="paper-reset">Reset paper ledger</button>`;
}

async function loadLive() {
  const el = $("tr-live");
  if (!el) return;
  const r = await call("live_status");
  if (!r.ok) { el.innerHTML = `<h3>Live Trading</h3><p class="tr-err small">${esc(r.error)}</p>`; return; }
  const d = r.data;
  const rows = d.brokers.map((b) => [esc(b.label), Object.values(b.keys).every(Boolean) ? `<span class="pos">keys set</span>` : `<span class="muted">keys not set</span>`, esc(b.adapter)]);
  el.innerHTML = `<h3>Live Trading <span class="h3-sub tr-off">${d.live_enabled ? "ENABLED IN CONFIG" : "OFF"}</span></h3>
    ${table(["Broker", "API keys", "Adapter"], rows)}
    <p class="muted small">Live orders need ALL of: live_trading_enabled in the config file (not switchable here), no STOP, this window, a broker adapter, and you typing <b>${esc(d.confirm_phrase)}</b> for each order. No adapter exists in this build, so nothing can reach a broker. Add broker keys in Settings → Keys &amp; brokers.</p>
    <div class="tr-order"><input id="tr-r4" placeholder="Type ${esc(d.confirm_phrase)}" autocomplete="off"/><button class="set-btn danger" data-act="live">Send LIVE order (R4)</button></div>
    <div id="tr-live-msg" class="small"></div>`;
}

async function onTradingClick(e) {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.sym) { tr.symbol = b.dataset.sym; tr.news = null; renderNews(); return loadTrading(); }
  if (b.dataset.tf) { tr.tf = b.dataset.tf; return loadTrading(); }
  const act = b.dataset.act;
  if (act === "refresh") return loadTrading();
  if (act === "paper-buy" || act === "paper-sell") {
    const qty = Math.max(1, Math.min(1000, parseInt(($("tr-qty") || {}).value || "1", 10) || 1));
    const coid = `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    b.disabled = true;
    const r = await call("paper_order", tr.symbol, act === "paper-buy" ? "BUY" : "SELL", qty, coid, "signal-ui");
    b.disabled = false;
    const m = $("tr-order-msg");
    if (m) m.innerHTML = r.ok ? `<span class="pos">PAPER ${esc(r.data.side)} ${nf(r.data.qty, 0)} ${esc(r.data.symbol)} @ ${nf(r.data.price)} — ${esc(r.data.id)}</span>` : `<span class="tr-err">${esc(r.error)}</span>`;
    return loadPaper();
  }
  if (act === "paper-reset") {
    if (!window.confirm("Clear the paper ledger? (virtual trades only)")) return;
    await call("paper_reset", true);
    return loadPaper();
  }
  if (act === "news") {
    tr.news = "loading"; renderNews();
    tr.news = await call("trading_news", tr.symbol); renderNews();
    return;
  }
  if (act === "live") {
    const typed = ($("tr-r4") || {}).value || "";
    const qty = Math.max(1, parseInt(($("tr-qty") || {}).value || "1", 10) || 1);
    const r = await call("live_order", tr.symbol, "BUY", qty, typed, "sahi");
    const m = $("tr-live-msg");
    if (m) m.innerHTML = r.ok ? `<span class="pos">Sent.</span>` : `<span class="tr-err">Refused (gate ${esc(r.gate ?? "?")}): ${esc(r.error)}</span>`;
    if ($("tr-r4")) $("tr-r4").value = "";
  }
}

// ---------------- Tasks: chain + persistent queue ----------------
export function renderTasksP3(el) {
  if (!el) return;
  if (!el.dataset.p3) {
    el.dataset.p3 = "1";
    el.innerHTML = `<div class="panel"><h3>Research → Analyst → Writer</h3>
      <div class="tr-order"><input id="chain-topic" placeholder="Topic, e.g. RBI policy impact on Bank Nifty this month" maxlength="300"/><button class="set-btn" data-act="chain">Run chain</button></div>
      <p class="muted small">Three real model calls (cloud first, local AI fallback). Research uses web search + memory; the Writer's report is saved to <code>workspace\\reports</code> and indexed into memory. STOP cancels it.</p><div id="chain-msg" class="small"></div></div>
      <div class="panel"><h3>Task queue <span class="h3-sub">persists across restarts</span></h3><div id="task-list"></div></div>`;
    el.addEventListener("click", onTasksClick);
  }
  loadTasks();
}

export async function loadTasks() {
  const el = $("task-list");
  if (!el) return;
  const r = await call("tasks_list", 20);
  if (!r.ok) { el.innerHTML = `<p class="tr-err small">${esc(r.error)}</p>`; return; }
  const ts = r.data.tasks;
  if (!ts.length) { el.innerHTML = `<p class="muted small">No tasks yet.</p>`; return; }
  el.innerHTML = ts.map((t) => {
    const steps = (t.steps || []).map((s) => `<span class="chip">${esc(s.agent)} · ${esc(s.provider)} · ${s.seconds}s</span>`).join("");
    const btns = ["error", "interrupted", "cancelled"].includes(t.state) && t.state !== "cancelled" ? `<button class="set-btn" data-act="retry" data-id="${t.id}">Retry</button>` : (["running", "queued"].includes(t.state) ? `<button class="set-btn" data-act="cancel" data-id="${t.id}">Cancel</button>` : "");
    const res = t.result ? `<button class="set-btn" data-act="open" data-path="workspace/reports">Open reports</button> <code class="small">${esc(t.result)}</code>` : "";
    return `<div class="task-row st-${t.state}"><div class="task-top"><b>${esc(t.title)}</b><span class="task-st">${esc(t.state)}${t.state === "running" ? ` · step ${t.step}/3` : ""}</span></div>
      <div class="small muted">${esc(t.kind)} · ${esc(t.source)} · ${esc((t.created || "").replace("T", " ").slice(0, 16))} IST${t.error ? ` · <span class="tr-err">${esc(t.error)}</span>` : ""}</div>
      <div class="task-steps">${steps}</div><div>${res} ${btns}</div></div>`;
  }).join("");
}

async function onTasksClick(e) {
  const b = e.target.closest("button");
  if (!b) return;
  const act = b.dataset.act;
  if (act === "chain") {
    const topic = ($("chain-topic") || {}).value || "";
    const r = await call("chain_start", topic, "ui");
    $("chain-msg").innerHTML = r.ok ? `<span class="pos">Started task ${esc(r.data.id)}.</span>` : `<span class="tr-err">${esc(r.error)}</span>`;
  } else if (act === "retry") await call("task_retry", b.dataset.id);
  else if (act === "cancel") await call("task_cancel", b.dataset.id);
  else if (act === "open") await call("open_folder", b.dataset.path);
  loadTasks();
}

// ---------------- Memory search ----------------
export function renderMemorySearch(el) {
  if (!el || el.dataset.p3) return;
  el.dataset.p3 = "1";
  el.innerHTML = `<div class="panel"><h3>Search memory</h3><div class="tr-order"><input id="mem-q" placeholder="Search notes, reports, journal, trade log…" maxlength="200"/><button class="set-btn" data-act="mem-search">Search</button><button class="set-btn" data-act="mem-reindex">Re-index files</button></div><div id="mem-stats" class="small muted"></div><div id="mem-results"></div></div>`;
  el.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.act === "mem-reindex") { b.textContent = "Indexing…"; const r = await call("memory_reindex"); b.textContent = "Re-index files"; $("mem-stats").textContent = r.ok ? `Indexed ${r.data.files} files (+${r.data.added} new, ${r.data.updated} changed) in ${r.data.seconds}s` : r.error; }
    memSearch();
  });
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.id === "mem-q") memSearch(); });
  memSearch();
}
async function memSearch() {
  const q = ($("mem-q") || {}).value || "";
  const r = await call("memory_search", q, 20);
  const out = $("mem-results");
  if (!out) return;
  if (!r.ok) { out.innerHTML = `<p class="tr-err small">${esc(r.error)}</p>`; return; }
  const s = r.data.stats;
  $("mem-stats").textContent = `${s.total} items (${Object.entries(s.by_kind).map(([k, v]) => `${k} ${v}`).join(", ") || "empty"}) · ${s.fts ? "full-text index" : "basic search"}`;
  out.innerHTML = r.data.results.length ? r.data.results.map((m) => `<div class="mem-hit"><div><b>${esc(m.title)}</b> <span class="chip">${esc(m.kind)}</span> <span class="muted small">${esc(m.source)}</span></div><div class="small muted">${esc(m.snippet)}</div></div>`).join("") : `<p class="muted small">${q ? "No matches." : "Nothing saved yet — chain reports, notes and paper trades appear here."}</p>`;
}

// ---------------- Settings ----------------
export function renderSettingsP3(host) {
  if (!host || host.dataset.p3) return;
  host.dataset.p3 = "1";
  host.insertAdjacentHTML("beforeend", `
    <div class="panel" id="p3-keys"><h3>Keys &amp; brokers</h3>
      <div class="tr-order"><select id="key-slot"></select><input id="key-custom" placeholder="JARVIS_MYSERVICE_API_KEY" maxlength="70" style="display:none"/>
      <input id="key-val" type="password" placeholder="Paste key (never shown again)" autocomplete="off"/><button class="set-btn" data-act="key-save">Save</button></div>
      <div id="key-msg" class="small"></div><div id="key-list"></div>
      <p class="muted small">Saved straight to Windows Credential Manager (<code>JARVIS/&lt;NAME&gt;</code>). Jarvis shows only whether a key is set — never its value. <b>Test</b> is a read-only check (account/profile/quote); it never places or tests an order. Broker keys do not enable live trading.</p></div>
    <div class="panel" id="p3-local"><h3>Local AI (Ollama)</h3><div id="lai-status" class="small"></div>
      <label class="set-row">Routing <select id="lai-mode"><option value="hybrid">Hybrid — cloud first, local fallback/offline</option><option value="local_first">Local first — then cloud</option><option value="cloud_only">Cloud only</option></select></label>
      <button class="set-btn" data-act="lai-test">Test local model</button><div id="lai-out" class="small"></div></div>
    <div class="panel" id="p3-api"><h3>Local API</h3><div id="api-status" class="small"></div>
      <button class="set-btn" data-act="api-copy">Copy token</button> <button class="set-btn" data-act="api-rotate">Rotate token</button><div id="api-msg" class="small"></div>
      <details><summary class="small">Endpoints</summary><div id="api-eps"></div></details></div>`);
  host.addEventListener("click", onSettingsClick);
  host.addEventListener("change", async (e) => {
    if (e.target.id === "key-slot") $("key-custom").style.display = e.target.value === "__custom" ? "" : "none";
    if (e.target.id === "lai-mode") { await call("settings_set", { ai_mode: e.target.value }); loadLocalAi(); }
  });
  refreshSettingsP3();
}
export function refreshSettingsP3() { loadKeys(); loadLocalAi(); loadApi(); }

async function loadKeys() {
  const r = await call("keys_status");
  const list = $("key-list"), sel = $("key-slot");
  if (!list) return;
  if (!r.ok) { list.innerHTML = `<p class="tr-err small">${esc(r.error)}</p>`; return; }
  const keys = r.data.keys;
  if (sel && !sel.dataset.filled) {
    sel.dataset.filled = "1";
    sel.innerHTML = keys.filter((k) => !k.custom).map((k) => `<option value="${esc(k.name)}">${esc(k.group)} — ${esc(k.label)}</option>`).join("") + `<option value="__custom">Custom name…</option>`;
  }
  list.innerHTML = table(["Key", "Status", ""], keys.map((k) => [`${esc(k.label)}<div class="muted small">${esc(k.name)}${k.used ? "" : " · stored only"}</div>`, k.set ? `<span class="pos">set</span> <span class="muted small">${esc(k.where)}</span>` : `<span class="muted">not set</span>`, `${k.test && k.set ? `<button class="set-btn" data-act="key-test" data-test="${esc(k.test)}">Test</button> ` : ""}${k.set && k.where === "credential_manager" ? `<button class="set-btn" data-act="key-del" data-name="${esc(k.name)}">Remove</button>` : ""}`]));
}

async function loadLocalAi() {
  const r = await call("local_ai_status");
  const el = $("lai-status");
  if (!el) return;
  if (!r.ok) { el.innerHTML = `<span class="tr-err">${esc(r.error)}</span>`; return; }
  const o = r.data.ollama;
  const st = { ready: `<span class="pos">ready</span> · model <b>${esc(o.model)}</b>`, no_models: `<span class="warn">running, no model pulled</span>`, not_running: `<span class="warn">Ollama not running</span>` }[o.state] || esc(o.state);
  el.innerHTML = `${st}<div class="muted">Installed: ${esc((o.models || []).join(", ") || "none")} · Order: ${esc(r.data.plan.join(" → ") || "none")} · cheap tasks: ${esc(r.data.plan_cheap.join(" → "))}</div>`;
  if ($("lai-mode")) $("lai-mode").value = r.data.ai_mode;
}

async function loadApi() {
  const r = await call("api_info");
  const el = $("api-status");
  if (!el) return;
  if (!r.ok) { el.innerHTML = `<span class="tr-err">${esc(r.error)}</span>`; return; }
  const d = r.data;
  el.innerHTML = `${d.running ? `<span class="pos">running</span>` : `<span class="warn">${d.enabled ? "not running" : "disabled"}</span>`} · <code>${esc(d.base)}</code> · ${d.requests} requests<div class="muted">Token: ${d.token_set ? "set" : "not set"} — ${esc(d.token_location)}. Header <code>Authorization: Bearer &lt;token&gt;</code>. 127.0.0.1 only; blocked during STOP; cannot approve R3/R4 or place orders.${d.error ? ` <span class="tr-err">${esc(d.error)}</span>` : ""}</div>`;
  const eps = $("api-eps");
  if (eps) eps.innerHTML = table(["Method", "Path", "What"], d.endpoints.map((e) => [esc(e.method), `<code>${esc(e.path)}</code>`, esc(e.desc)]));
}

async function onSettingsClick(e) {
  const b = e.target.closest("button");
  if (!b || !b.dataset.act) return;
  const act = b.dataset.act;
  if (act === "key-save") {
    let name = $("key-slot").value;
    if (name === "__custom") name = ($("key-custom").value || "").trim().toUpperCase();
    const val = $("key-val").value;
    $("key-val").value = "";
    const r = await call("key_set", name, val);
    $("key-msg").innerHTML = r.ok ? `<span class="pos">${esc(r.data.name)} saved to Credential Manager.</span>` : `<span class="tr-err">${esc(r.error)}</span>`;
    loadKeys(); loadLocalAi();
  } else if (act === "key-del") {
    if (!window.confirm(`Remove ${b.dataset.name} from Credential Manager?`)) return;
    await call("key_delete", b.dataset.name, true);
    loadKeys();
  } else if (act === "key-test") {
    $("key-msg").textContent = `Testing ${b.dataset.test} (read-only)…`;
    const r = await call("key_test", b.dataset.test);
    const d = r.ok ? r.data : { ok: false, status: "error", detail: r.error };
    $("key-msg").innerHTML = `<b>${esc(b.dataset.test)}</b>: <span class="${d.ok ? "pos" : "tr-err"}">${esc(d.status)}</span>${d.latency_ms !== undefined ? ` · ${d.latency_ms} ms` : ""} · ${esc(d.detail || "")}`;
  } else if (act === "lai-test") {
    $("lai-out").textContent = "Asking the local model… (CPU, ~5–20 s)";
    const r = await call("local_ai_test", "");
    $("lai-out").innerHTML = r.ok ? `<b>${esc(r.data.model)}</b> (${r.data.seconds}s): ${esc(r.data.text)}` : `<span class="tr-err">${esc(r.error)}</span>`;
  } else if (act === "api-copy") {
    const r = await call("api_token_copy");
    $("api-msg").innerHTML = r.ok ? `<span class="pos">Token copied to clipboard.</span>` : `<span class="tr-err">${esc(r.error)}</span>`;
  } else if (act === "api-rotate") {
    if (!window.confirm("Rotate the local API token? Scripts using the old token will stop working.")) return;
    const r = await call("api_token_rotate", true);
    $("api-msg").innerHTML = r.ok ? `<span class="pos">New token saved.</span>` : `<span class="tr-err">${esc(r.error)}</span>`;
    loadApi();
  }
}
