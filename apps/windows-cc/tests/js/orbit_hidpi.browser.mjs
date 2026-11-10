// Real-browser regression test for the 3D orbit canvases on HiDPI screens (Windows 125% scaling).
// Bug (Nov 2026): orbit3d fit() read clientWidth of the CSS-unsized Home #sphere canvas and wrote
// width = clientWidth * devicePixelRatio every frame -> canvas grew 25%/frame to 33,554,432 px,
// nothing rendered, WebView2 reached ~2 GB and closed.
// Nov 2026 (hero core): the Home core must fill >= 55% of the hero and stay a stable size per frame.
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
  for (const dpr of [1, 1.25, 1.5]) {
    const pg = await b.newPage({ viewport: { width: 1500, height: 950 }, deviceScaleFactor: dpr });
    const errs = [];
    pg.on("pageerror", (e) => errs.push(e.message));
    await pg.addInitScript(() => {
      const agents = ["coding", "research", "memory", "browser", "task", "system", "builder", "video"]
        .map((id) => ({ id, name: id, state: "idle", steps: [] }));
      window.pywebview = { api: new Proxy({}, { get: (_, k) => async () =>
        (k === "agents" ? { ok: true, data: { agents } } : { ok: true, data: {} }) }) };
    });
    await pg.goto(`http://127.0.0.1:${port}/index.html`);
    await pg.waitForTimeout(2500);
    // Hero AI Core: sample size over several frames -> must be large AND stable (no feedback loop).
    const samples = [];
    for (let k = 0; k < 4; k++) {
      samples.push(await pg.evaluate(() => { const s = document.getElementById("sphere");
        const r = s.getBoundingClientRect(); const hero = document.querySelector(".hero").getBoundingClientRect();
        const st = (window.__orbitStats || {}).sphere || {};
        return { w: s.width, h: s.height, cw: Math.round(r.width), ch: Math.round(r.height),
          heroW: Math.round(hero.width), heroH: Math.round(hero.height), main: document.getElementById("main").clientHeight,
          frames: st.frames || 0, core: st.coreDiamPx || 0, reactor: st.reactorDiamPx || 0,
          labels: document.querySelectorAll("#home-orbit-labels .orbit-label").length }; }));
      await pg.waitForTimeout(400);
    }
    const home = samples[samples.length - 1];
    await pg.click('#nav button[data-route="agents"]');
    await pg.waitForTimeout(2000);
    const ag = await pg.evaluate(() => { const s = document.getElementById("agents-orbit");
      return { w: s.width, h: s.height, cw: s.clientWidth, ch: s.clientHeight,
        labels: document.querySelectorAll("#orbit-labels .orbit-label").length }; });
    const tag = `dpr ${dpr}`;
    const areaRatio = (home.cw * home.ch) / (home.heroW * home.heroH);
    if (areaRatio < 0.55) fail.push(`${tag}: Home core canvas is ${(areaRatio * 100).toFixed(0)}% of the hero area, want >= 55%`);
    if (home.ch < 0.55 * home.main) fail.push(`${tag}: Home core ${home.ch}px tall is < 55% of Home content height ${home.main}`);
    if (samples.some((x) => x.w !== home.w || x.h !== home.h || x.cw !== home.cw || x.ch !== home.ch))
      fail.push(`${tag}: Home core size changed between frames ${JSON.stringify(samples.map((x) => [x.w, x.h, x.cw, x.ch]))}`);
    if (Math.abs(home.w - Math.floor(home.cw * dpr)) > 2) fail.push(`${tag}: Home backing ${home.w} != css ${home.cw} * dpr`);
    if (home.w > 2048 || home.h > 2048) fail.push(`${tag}: Home backing store ${home.w}x${home.h} > 2048`);
    if (!(home.frames > 1)) fail.push(`${tag}: Home core not rendering (frames ${home.frames})`);
    if (home.core < 0.22 * home.ch) fail.push(`${tag}: core sphere only ${home.core}px on a ${home.ch}px stage`);
    if (home.reactor < 0.55 * home.ch) fail.push(`${tag}: reactor rings only ${home.reactor}px on a ${home.ch}px stage`);
    if (home.labels !== 8) fail.push(`${tag}: ${home.labels} Home orbit labels, want 8`);
    if (Math.abs(ag.w - Math.floor(ag.cw * dpr)) > 2) fail.push(`${tag}: Agents canvas ${ag.w} != css ${ag.cw} * dpr`);
    if (ag.cw < 200 || ag.ch < 200) fail.push(`${tag}: Agents canvas too small ${ag.cw}x${ag.ch}`);
    if (ag.labels !== 8) fail.push(`${tag}: ${ag.labels} orbit labels, want 8`);
    if (errs.length) fail.push(`${tag}: page errors ${errs.join(" | ")}`);
    console.log(tag, JSON.stringify({ home, ag }));
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
