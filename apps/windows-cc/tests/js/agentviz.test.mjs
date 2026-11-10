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
