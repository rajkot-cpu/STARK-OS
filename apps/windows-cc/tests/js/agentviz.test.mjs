// Pure state -> visual logic for the 3D agent orbit (ui/js/agentviz.js).
import test from "node:test";
import assert from "node:assert/strict";
import {
  classify, visualFor, Tracker, orbitFor, styleFor, FrameGate, FLASH_MS,
} from "../../ui/js/agentviz.js";

test("classify maps real hub states", () => {
  assert.equal(classify({ state: "active" }), "working");
  assert.equal(classify({ state: "standby" }), "idle");
  assert.equal(classify({ state: "error" }), "error");
  assert.equal(classify({ state: "standby", pending: { token: "x" } }), "waiting");
  assert.equal(classify({ state: "standby", detail: "needs_r3:git push" }), "waiting");
  assert.equal(classify({ state: "weird" }), "idle");
  assert.equal(classify(null), "idle");
});

test("idle is dim and slow; working bright, pulsing, beamed and faster", () => {
  const idle = visualFor("idle");
  const work = visualFor("working");
  assert.ok(idle.intensity < 0.5);
  assert.ok(work.intensity > idle.intensity);
  assert.ok(work.speed > idle.speed * 2);
  assert.equal(idle.beam, false);
  assert.equal(work.beam, true);
  assert.equal(idle.pulse, false);
  assert.equal(work.pulse, true);
  assert.equal(idle.tint, null);
});

test("flashes override tint: error red, done green", () => {
  assert.equal(visualFor("idle", "done").tint, 0x3dff9a);
  assert.equal(visualFor("error", "error").tint, 0xff3b3b);
  assert.equal(visualFor("error").tint, 0xff3b3b); // steady error stays red-ish
  assert.equal(visualFor("waiting").tint, 0xffc14d);
});

test("tracker: active->standby gives a short done flash", () => {
  const t = new Tracker();
  assert.equal(t.update("builder", "working", 0), null); // first sight: no flash
  assert.equal(t.update("builder", "idle", 1000), "done");
  assert.equal(t.flash("builder", 1000 + FLASH_MS - 1), "done");
  assert.equal(t.flash("builder", 1000 + FLASH_MS + 1), null);
});

test("tracker: any -> error flashes red; first sight in error flashes too", () => {
  const t = new Tracker();
  t.update("video", "working", 0);
  assert.equal(t.update("video", "error", 10), "error");
  const t2 = new Tracker();
  assert.equal(t2.update("x", "error", 0), "error");
  assert.equal(t2.update("x", "error", 5), null); // no re-flash while it stays in error
});

test("tracker: idle->idle and working->waiting do not flash", () => {
  const t = new Tracker();
  t.update("a", "idle", 0);
  assert.equal(t.update("a", "idle", 1), null);
  t.update("b", "working", 0);
  assert.equal(t.update("b", "waiting", 1), null);
});

test("orbits are distinct per agent", () => {
  const n = 8;
  const os = Array.from({ length: n }, (_, i) => orbitFor(i, n));
  const radii = new Set(os.map((o) => o.radius.toFixed(3)));
  assert.equal(radii.size, n);
  os.forEach((o) => { assert.ok(o.radius > 1.3); assert.ok(Number.isFinite(o.tilt)); });
});

test("styles are distinct for the known agents and stable for unknown", () => {
  const ids = ["coding", "research", "memory", "browser", "task", "system", "builder", "video"];
  const shapes = new Set(ids.map((i) => styleFor(i).shape));
  const colors = new Set(ids.map((i) => styleFor(i).color));
  assert.equal(shapes.size, ids.length);
  assert.equal(colors.size, ids.length);
  assert.deepEqual(styleFor("zzz"), styleFor("zzz"));
});

test("frame gate caps at 60fps and pauses when hidden", () => {
  const g = new FrameGate(60);
  assert.equal(g.ok(0, true), true);
  assert.equal(g.ok(5, true), false);
  assert.equal(g.ok(17, true), true);
  assert.equal(g.ok(100, false), false);
});

import { canvasCssSize, MAX_CANVAS_CSS } from "../../ui/js/agentviz.js";

test("canvasCssSize uses the pinned size, never the DPR-scaled backing store", () => {
  // Home core: pinned 320x320 even if the layout reports something else.
  assert.deepEqual(canvasCssSize(400, 400, { w: 320, h: 320 }), { w: 320, h: 320 });
  // Fluid canvas follows layout.
  assert.deepEqual(canvasCssSize(812, 440), { w: 812, h: 440 });
  // Not laid out yet -> sane default.
  assert.deepEqual(canvasCssSize(0, 0), { w: 320, h: 320 });
  // Runaway values are clamped (the PC hit 26,843,546 css px).
  assert.deepEqual(canvasCssSize(26843546, 26843546), { w: MAX_CANVAS_CSS, h: MAX_CANVAS_CSS });
});

test("repeated fit at dpr 1.25 is a fixed point for the pinned core", () => {
  let client = 320;
  for (let i = 0; i < 100; i++) {
    const { w } = canvasCssSize(client, client, { w: 320, h: 320 });
    const backing = Math.round(w * 1.25); // three.js setSize(w, h, false) -> canvas.width
    client = backing / 1.25;              // what layout reports once the style is pinned
  }
  assert.equal(client, 320);
});

import { badgeFor, damp, corePulse } from "../../ui/js/agentviz.js";

test("badgeFor gives the state badge text", () => {
  assert.equal(badgeFor("idle"), "IDLE");
  assert.equal(badgeFor("working"), "WORKING");
  assert.equal(badgeFor("waiting"), "APPROVAL");
  assert.equal(badgeFor("error"), "ERROR");
  assert.equal(badgeFor("idle", "done"), "DONE");
  assert.equal(badgeFor("idle", "error"), "ERROR");
  assert.equal(badgeFor("weird"), "IDLE");
});

test("damp moves toward the target, frame-rate independent, never overshoots", () => {
  assert.equal(damp(0, 1, 6, 0), 0);
  const a = damp(0, 1, 6, 1 / 60);
  assert.ok(a > 0 && a < 1);
  // two half steps == one full step
  const half = damp(damp(0, 1, 6, 1 / 120), 1, 6, 1 / 120);
  assert.ok(Math.abs(half - a) < 1e-9);
  assert.ok(Math.abs(damp(0, 1, 6, 10) - 1) < 1e-9);
  assert.equal(damp(5, 5, 6, 0.1), 5);
});

test("corePulse grows with working agents and stays bounded", () => {
  const idle = corePulse(0, 0);
  const busy = corePulse(3, 0);
  assert.ok(busy.intensity > idle.intensity);
  assert.ok(busy.rate > idle.rate);
  const many = corePulse(50, 1234);
  assert.ok(many.intensity <= 1 && many.rate <= 6 && many.scale <= 1.25 && many.scale >= 0.9);
  for (let t = 0; t < 5000; t += 37) {
    const p = corePulse(2, t);
    assert.ok(p.scale >= 0.9 && p.scale <= 1.25);
  }
});

import { backingFor, MAX_BACKING, cameraDistance, voicePulse } from "../../ui/js/agentviz.js";

test("backingFor follows DPR and caps the backing store at MAX_BACKING", () => {
  assert.deepEqual(backingFor(800, 600, 1.25), { w: 800, h: 600, pr: 1.25, bw: 1000, bh: 750 });
  assert.equal(backingFor(800, 600, 3).pr, 2);
  const big = backingFor(1900, 1000, 1.5);
  assert.ok(big.bw <= MAX_BACKING && big.bh <= MAX_BACKING, JSON.stringify(big));
  const huge = backingFor(26843546, 26843546, 1.25);
  assert.ok(huge.bw <= MAX_BACKING && huge.bh <= MAX_BACKING);
  assert.equal(backingFor(0, 0, 1).w, 320);
});

test("backingFor is idempotent: feeding its result back never grows (no feedback loop)", () => {
  let css = { w: 900, h: 640 };
  for (const dpr of [1, 1.25, 1.5]) {
    const a = backingFor(css.w, css.h, dpr);
    const b = backingFor(a.w, a.h, dpr);
    assert.deepEqual(a, b);
  }
});

test("cameraDistance fits both the height and the width", () => {
  const tall = cameraDistance(0.6, 38, 3, 4);
  const wide = cameraDistance(2.0, 38, 3, 4);
  assert.ok(tall > wide, "narrow canvases need the camera further away");
  const t = Math.tan((38 * Math.PI) / 360);
  assert.ok(Math.abs(wide - 3 / t) < 1e-9);
});

test("voicePulse: idle calm, listening pulls energy in, speaking flickers within 0..1", () => {
  assert.deepEqual(voicePulse("idle", 1000), { amp: 0, flow: 1 });
  assert.ok(voicePulse("listening", 1000).flow > 2);
  const amps = Array.from({ length: 200 }, (_, i) => voicePulse("speaking", i * 16).amp);
  assert.ok(Math.min(...amps) >= 0 && Math.max(...amps) <= 1);
  assert.ok(Math.max(...amps) - Math.min(...amps) > 0.3, "speaking should visibly vary");
});

test("orbitFor accepts a larger hero base radius", () => {
  const o = orbitFor(0, 8, 2.4, 0.2, 0.7);
  assert.equal(o.radius, 2.4);
  assert.ok(Math.abs(orbitFor(7, 8, 2.4, 0.2).radius - 3.8) < 1e-9);
});
