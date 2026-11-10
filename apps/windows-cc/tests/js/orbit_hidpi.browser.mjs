// Real-browser regression test for the 3D orbit canvases on HiDPI screens (Windows 125% scaling).
// Bug (Nov 2026): orbit3d fit() read clientWidth of the CSS-unsized Home #sphere canvas and wrote
// width = clientWidth * devicePixelRatio every frame -> canvas grew 25%/frame to 33,554,432 px,
// nothing rendered, WebView2 reached ~2 GB and closed.
// Nov 2026 (hero v2): at 1024x606, 1366x768 and 1920x1080 (DPR 1/1.25/1.5) the sphere is >= 35% of the stage
// height, agent nodes >= 40 px, labels never overlap, the stage gets >= 60% of the width, focus mode fills the page.
// Usage: node orbit_hidpi.browser.mjs <ui dir> <playwright-core dir> <chrome path>
import { createRequire } from "node:module";
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
const [uiDir, pwDir, chrome] = process.argv.slice(2);
const { chromium } = createRequire(path.join(pwDir, "x.js"))("playwright-core");
const types = { ".js": "text/javascript", ".html": "text/html", ".css": "text/css" };
const srv = http.createServer((q, s) => {
  const p = path.join(uiDir, decodeURIComponent(q.url.split("?")[0]));
  fs.readFile(p, (e, d) => { if (e) { s.writeHead(404); s.end(); return; }
    s.writeHead(200, { "content-type": types[path.extname(p)] || "application/octet-stream" }); s.end(d); });
}).listen(0);
const port = srv.address().port;
const fail = [];
const b = await chromium.launch({ executablePath: chrome,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
try {
  // Hero v2 (Nov 2026): real-Chrome layout at the PC's window sizes and scalings.
  for (const [vw, vh] of [[1024, 606], [1366, 768], [1920, 1080]]) for (const dpr of [1, 1.25, 1.5]) {
    const pg = await b.newPage({ viewport: { width: vw, height: vh }, deviceScaleFactor: dpr });
    const errs = [];
    pg.on("pageerror", (e) => errs.push(e.message));
    await pg.addInitScript(() => {
      const agents = ["coding", "research", "memory", "browser", "task", "system", "builder", "video"]
        .map((id, i) => ({ id, name: id[0].toUpperCase() + id.slice(1) + " Agent", state: i === 1 || i === 6 ? "active" : "standby",
          pending: i === 3 ? { token: "t", label: "x" } : null, steps: [] }));
      window.pywebview = { api: new Proxy({}, { get: (_, k) => async () =>
        (k === "agents" ? { ok: true, data: { agents } } : { ok: true, data: {} }) }) };
    });
    await pg.goto(`http://127.0.0.1:${port}/index.html`);
    await pg.waitForTimeout(2500);
    // sample over several frames: size must be stable; labels must never overlap each other
    const samples = [];
    let overlaps = 0, overlapInfo = "";
    for (let k = 0; k < 5; k++) {
      const smp = await pg.evaluate(() => { const s = document.getElementById("sphere");
        const r = s.getBoundingClientRect(); const stage = document.getElementById("core-stage").getBoundingClientRect();
        const st = (window.__orbitStats || {}).sphere || {};
        const rects = [...document.querySelectorAll("#home-orbit-labels .orbit-label")].map((l) => {
          const q = l.getBoundingClientRect(); return { x: q.left, y: q.top, w: q.width, h: q.height, id: l.dataset.orbitAgent }; });
        const bad = [];
        for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
          const A = rects[i], B = rects[j];
          if (Math.min(A.x + A.w, B.x + B.w) - Math.max(A.x, B.x) > 1 && Math.min(A.y + A.h, B.y + B.h) - Math.max(A.y, B.y) > 1) bad.push(A.id + "/" + B.id);
        }
        return { w: s.width, h: s.height, cw: Math.round(r.width), ch: Math.round(r.height), stageW: Math.round(stage.width),
          contentW: document.getElementById("main").clientWidth, frames: st.frames || 0, core: st.coreDiamPx || 0,
          nodeMin: st.nodeMinPx || 0, labels: rects.length, bad }; });
      samples.push(smp);
      if (smp.bad.length) { overlaps++; overlapInfo = smp.bad.join(","); }
      await pg.waitForTimeout(350);
    }
    const home = samples[samples.length - 1];
    const tag = `${vw}x${vh} dpr ${dpr}`;
    if (home.core < 0.35 * home.ch) fail.push(`${tag}: core sphere ${home.core}px is < 35% of the ${home.ch}px stage`);
    if (home.nodeMin < 40) fail.push(`${tag}: smallest agent node ${home.nodeMin}px < 40px`);
    if (overlaps) fail.push(`${tag}: labels overlapped in ${overlaps}/5 samples (${overlapInfo})`);
    if (home.stageW < 0.6 * (home.contentW - 24)) fail.push(`${tag}: stage ${home.stageW}px is < 60% of the content width ${home.contentW}`);
    if (samples.some((x) => x.w !== home.w || x.h !== home.h || x.cw !== home.cw || x.ch !== home.ch))
      fail.push(`${tag}: Home core size changed between frames ${JSON.stringify(samples.map((x) => [x.w, x.h, x.cw, x.ch]))}`);
    if (Math.abs(home.w - Math.floor(home.cw * Math.min(2, dpr))) > 2) fail.push(`${tag}: Home backing ${home.w} != css ${home.cw} * dpr`);
    if (home.w > 2048 || home.h > 2048) fail.push(`${tag}: Home backing store ${home.w}x${home.h} > 2048`);
    if (!(home.frames > 1)) fail.push(`${tag}: Home core not rendering (frames ${home.frames})`);
    if (home.labels !== 8) fail.push(`${tag}: ${home.labels} Home orbit labels, want 8`);
    // focus mode: the core fills the whole content area
    await pg.click("#btn-focus");
    await pg.waitForTimeout(600);
    const fm = await pg.evaluate(() => ({ stage: document.getElementById("core-stage").getBoundingClientRect().width,
      main: document.getElementById("main").clientWidth, feed: document.querySelector(".feed").offsetParent !== null }));
    if (fm.stage < fm.main - 40 || fm.feed) fail.push(`${tag}: focus mode does not fill the content area ${JSON.stringify(fm)}`);
    await pg.keyboard.press("Escape");
    if (vw === 1366 && dpr === 1.25) {
      await pg.click('#nav button[data-route="agents"]');
      await pg.waitForTimeout(2000);
      const ag = await pg.evaluate(() => { const s = document.getElementById("agents-orbit");
        return { w: s.width, h: s.height, cw: s.clientWidth, ch: s.clientHeight,
          labels: document.querySelectorAll("#orbit-labels .orbit-label").length }; });
      if (Math.abs(ag.w - Math.floor(ag.cw * dpr)) > 2) fail.push(`${tag}: Agents canvas ${ag.w} != css ${ag.cw} * dpr`);
      if (ag.cw < 200 || ag.ch < 200) fail.push(`${tag}: Agents canvas too small ${ag.cw}x${ag.ch}`);
      if (ag.labels !== 8) fail.push(`${tag}: ${ag.labels} orbit labels, want 8`);
    }
    if (errs.length) fail.push(`${tag}: page errors ${errs.join(" | ")}`);
    console.log(tag, JSON.stringify({ ...home, bad: undefined, overlaps }));
    await pg.close();
  }
  // A failing ES module import must be logged (it used to be completely silent).
  {
    const pg = await b.newPage();
    await pg.addInitScript(() => {
      window.__logs = [];
      window.pywebview = { api: new Proxy({}, { get: (_, k) => async (...a) => {
        if (k === "ui_log") window.__logs.push(a.join(" ")); return { ok: true, data: {} }; } }) };
    });
    await pg.route("**/vendor/three.module.js", (r) => r.fulfill({ status: 404, body: "" }));
    await pg.goto(`http://127.0.0.1:${port}/index.html`);
    await pg.waitForTimeout(11000);
    const r = await pg.evaluate(() => ({ logs: window.__logs, banner: document.getElementById("banner").textContent }));
    if (!r.logs.some((l) => /never started|failed to load/.test(l))) fail.push(`module failure not logged: ${JSON.stringify(r.logs)}`);
    if (!/failed to start/.test(r.banner)) fail.push(`no banner on module failure: "${r.banner}"`);
    console.log("module-fail", JSON.stringify(r));
    await pg.close();
  }
  // A slow/missing bridge method reports "offline": the talk bar must explain it calmly (not a red "offline"),
  // and quiet hours must not look like an error.
  {
    const pg = await b.newPage();
    await pg.addInitScript(() => {
      window.pywebview = { api: new Proxy({}, { get: (_, k) => async () =>
        (k === "status" ? { ok: false, error: "offline" } : { ok: true, data: {} }) }) };
    });
    await pg.goto(`http://127.0.0.1:${port}/index.html`);
    await pg.waitForTimeout(2500);
    const r = await pg.evaluate(() => ({ text: document.getElementById("banner").textContent, cls: document.getElementById("banner").className }));
    if (/^offline$/i.test(r.text) || /err/.test(r.cls) || !/starting/.test(r.text)) fail.push(`offline banner: ${JSON.stringify(r)}`);
    await pg.close();
    const pq = await b.newPage();
    await pq.addInitScript(() => {
      window.pywebview = { api: new Proxy({}, { get: (_, k) => async () =>
        (k === "status" ? { ok: true, data: { system_status: "QUIET HOURS", quiet_hours: true, policy_ok: true } } : { ok: true, data: {} }) }) };
    });
    await pq.goto(`http://127.0.0.1:${port}/index.html`);
    await pq.waitForTimeout(2500);
    const q = await pq.evaluate(() => ({ pill: document.getElementById("sys-pill").className, sys: document.getElementById("hud-sys").className,
      banner: document.getElementById("banner").textContent }));
    if (/bad/.test(q.pill) || !/quiet/.test(q.pill) || /bad/.test(q.sys) || q.banner) fail.push(`quiet hours styled as an error: ${JSON.stringify(q)}`);
    console.log("offline/quiet", JSON.stringify({ r, q }));
    await pq.close();
  }
  // No WebGL -> visible message in the core panel instead of a blank square, and it is logged.
  {
    const pg = await b.newPage();
    await pg.addInitScript(() => {
      window.__logs = [];
      window.pywebview = { api: new Proxy({}, { get: (_, k) => async (...a) => {
        if (k === "ui_log") window.__logs.push(a.join(" ")); return { ok: true, data: {} }; } }) };
      const orig = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (t, ...rest) { return /webgl/.test(t) ? null : orig.call(this, t, ...rest); };
    });
    await pg.goto(`http://127.0.0.1:${port}/index.html`);
    await pg.waitForTimeout(2500);
    const r = await pg.evaluate(() => ({ logs: window.__logs,
      fb: [...document.querySelectorAll(".gl-fallback")].map((d) => d.textContent) }));
    if (r.fb.length < 2) fail.push(`no WebGL fallback messages: ${JSON.stringify(r)}`);
    if (!r.logs.some((l) => /WebGL init failed/.test(l))) fail.push(`WebGL failure not logged: ${JSON.stringify(r.logs)}`);
    console.log("no-webgl", JSON.stringify(r).slice(0, 400));
    await pg.close();
  }
} finally { await b.close(); srv.close(); }
if (fail.length) { console.error("FAIL\n" + fail.join("\n")); process.exit(1); }
console.log("OK");
