// apps/windows-cc/ui/js/agentviz.js — pure state -> visual logic for the 3D agent orbit.
// No DOM / Three.js here so it can be unit-tested with node (tests/js/agentviz.test.mjs).

export const FLASH_MS = 1400;
export const RED = 0xff3b3b;
export const GREEN = 0x3dff9a;
export const AMBER = 0xffc14d;

// Distinct shape + colour per fixed agent (agents/registry.py ROLES).
const STYLES = {
  coding:   { shape: "box",       color: 0x38d4ff },
  research: { shape: "icosa",     color: 0xb18cff },
  memory:   { shape: "torus",     color: 0xff7ad9 },
  browser:  { shape: "sphere",    color: 0x4dd2a6 },
  task:     { shape: "tetra",     color: 0xffd166 },
  system:   { shape: "octa",      color: 0x7aa8ff },
  builder:  { shape: "cone",      color: 0xff9f43 },
  video:    { shape: "torusKnot", color: 0xff5c8a },
};
const FALLBACK_SHAPES = ["dodeca", "cylinder", "box", "octa"];

export function styleFor(id) {
  if (STYLES[id]) return STYLES[id];
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return { shape: FALLBACK_SHAPES[h % FALLBACK_SHAPES.length], color: 0x80ffff ^ (h & 0x3f3f3f) };
}

/** Map one agent row from bridge `agents()` to a visual state. */
export function classify(agent) {
  if (!agent) return "idle";
  if (agent.state === "error") return "error";
  if (agent.state === "active") return "working";
  if (agent.pending || String(agent.detail || "").startsWith("needs_r3:")) return "waiting";
  return "idle";
}

/** Visual parameters for a state (+ optional transient flash). */
export function visualFor(state, flash = null) {
  let v;
  switch (state) {
    case "working":
      v = { intensity: 1.0, speed: 1.6, pulse: true, beam: true, tint: null, scale: 1.25 };
      break;
    case "waiting":
      v = { intensity: 0.8, speed: 0.35, pulse: true, beam: true, tint: AMBER, scale: 1.1 };
      break;
    case "error":
      v = { intensity: 0.75, speed: 0.25, pulse: false, beam: false, tint: RED, scale: 1.0 };
      break;
    default:
      v = { intensity: 0.32, speed: 0.4, pulse: false, beam: false, tint: null, scale: 1.0 };
  }
  if (flash === "error") v = { ...v, tint: RED, intensity: 1.0, scale: 1.35 };
  if (flash === "done") v = { ...v, tint: GREEN, intensity: 1.0, scale: 1.35 };
  return v;
}

/** Detects transitions between polls and keeps short-lived flashes. */
export class Tracker {
  constructor() { this.prev = {}; this.flashes = {}; }
  update(id, state, now) {
    const before = this.prev[id];
    this.prev[id] = state;
    let f = null;
    if (state === "error" && before !== "error") f = "error";
    else if ((before === "working" || before === "waiting") && state === "idle") f = "done";
    if (f) this.flashes[id] = { kind: f, until: now + FLASH_MS };
    return f;
  }
  flash(id, now) {
    const f = this.flashes[id];
    if (!f) return null;
    if (now > f.until) { delete this.flashes[id]; return null; }
    return f.kind;
  }
}

/** Each agent gets its own orbit: radius, tilt, node phase and direction. */
export function orbitFor(i, n, base = 1.45, step = 0.22, tiltScale = 1) {
  const k = Math.max(1, n);
  return {
    radius: base + i * step,
    tilt: (((i % 4) - 1.5) * 0.32 + (i % 2 ? 0.15 : -0.15)) * tiltScale,
    yaw: (i / k) * Math.PI,
    phase: (i / k) * Math.PI * 2,
    dir: i % 2 ? -1 : 1,
  };
}

/** Caps rendering to `fps` and skips frames when the view is hidden. */
export class FrameGate {
  constructor(fps = 60) { this.min = 1000 / fps - 0.5; this.last = -Infinity; }
  ok(now, visible) {
    if (!visible) return false;
    if (now - this.last < this.min) return false;
    this.last = now;
    return true;
  }
}

/** Largest drawing size (CSS px) a 3D canvas may take; guards against runaway resize loops. */
export const MAX_CANVAS_CSS = 2048;

/**
 * CSS size to render a canvas at. `fixed` = the size the canvas was pinned to at mount (Home core),
 * otherwise the laid-out client size (Agents page, 100% wide). Never reads the backing-store size,
 * which three.js multiplies by devicePixelRatio (reading it back grew the canvas every frame).
 */
export function canvasCssSize(clientW, clientH, fixed = null) {
  const pick = (v, f) => (fixed && fixed[f] > 0 ? fixed[f] : (v > 0 ? v : 320));
  const clamp = (v) => Math.max(1, Math.min(MAX_CANVAS_CSS, Math.round(v)));
  return { w: clamp(pick(clientW, "w")), h: clamp(pick(clientH, "h")) };
}

const BADGES = { idle: "IDLE", working: "WORKING", waiting: "APPROVAL", error: "ERROR" };
/** Short state badge for an agent label (a transient flash wins). */
export function badgeFor(state, flash = null) {
  if (flash === "done") return "DONE";
  if (flash === "error") return "ERROR";
  return BADGES[state] || "IDLE";
}

/** Exponential smoothing toward `target`; frame-rate independent (rate = 1/seconds). */
export function damp(current, target, rate, dt) {
  if (!(dt > 0)) return current;
  return target + (current - target) * Math.exp(-rate * dt);
}

/** AI Core heartbeat: faster and brighter the more agents are working. `t` in ms. */
export function corePulse(working, t) {
  const w = Math.max(0, Math.min(5, Number(working) || 0));
  const rate = 0.9 + w * 0.9;                       // beats per second-ish, <= 5.4
  const intensity = Math.min(1, 0.45 + w * 0.13);    // 0.45 .. 1
  const beat = 0.5 + 0.5 * Math.sin((t / 1000) * rate * Math.PI);
  const scale = 1 + (0.04 + w * 0.025) * beat;       // 1 .. <= 1.165
  return { rate, intensity, beat, scale };
}

/** Hard cap on a 3D canvas backing store (device px, either side). */
export const MAX_BACKING = 2048;

/**
 * Backing-store plan for a canvas laid out at cssW x cssH (taken from its PARENT's layout box,
 * never from the canvas itself). Pixel ratio is the screen DPR (<= 2), lowered so neither side
 * exceeds MAX_BACKING device px.
 */
export function backingFor(cssW, cssH, dpr) {
  const { w, h } = canvasCssSize(cssW, cssH);
  const want = Math.min(2, Math.max(1, Number(dpr) || 1));
  const pr = Math.min(want, MAX_BACKING / Math.max(w, h));
  return { w, h, pr, bw: Math.floor(w * pr), bh: Math.floor(h * pr) };
}

/** Camera distance so a scene of half-height `rv` and half-width `rh` fits a `vfovDeg` camera. */
export function cameraDistance(aspect, vfovDeg, rv, rh) {
  const t = Math.tan((vfovDeg * Math.PI) / 360);
  return Math.max(rv / t, rh / (t * Math.max(0.2, Number(aspect) || 1)));
}

/**
 * Core reaction to voice: `amp` 0..1 drives core/corona swell, `flow` multiplies the energy
 * streams. idle breathes only; listening draws energy in; speaking flickers like a voice. `t` ms.
 */
export function voicePulse(state, t) {
  if (state === "speaking") {
    const a = Math.abs(Math.sin(t / 95) * Math.sin(t / 61 + 1.3)) * 0.7 + 0.3 * (0.5 + 0.5 * Math.sin(t / 37));
    return { amp: Math.min(1, Math.max(0, a)), flow: 1.7 };
  }
  if (state === "listening") return { amp: 0.35 + 0.15 * (0.5 + 0.5 * Math.sin(t / 240)), flow: 2.4 };
  return { amp: 0, flow: 1 };
}

// ---------------- Hero v2: single clean outer orbit + collision-aware labels ----------------

/** Even spacing of `n` agents on ONE shared outer orbit (phase in radians). */
export function ringPhase(i, n) {
  const k = Math.max(1, n);
  return (i / k) * Math.PI * 2 + Math.PI / 2;
}

/**
 * Stage plan for the hero reactor, in CSS px. World units: the core shell has radius 1.
 *  k      px per world unit at the core (sphere diameter = 2k)
 *  R      world radius of the shared agent orbit
 *  elev   camera elevation (rad): projected orbit half-height = R*k*sin(elev)
 *  dy     how far the core sits below the stage centre (to clear the title strip)
 * Constraints: sphere ~40-45% of the stage height; the orbit ellipse clears the reactor rings
 * vertically (b >= clearR*k) and stays inside the stage with room for labels at the left/right ends.
 */
export function stagePlan(w, h, o = {}) {
  const padTop = o.padTop ?? 44, padBottom = o.padBottom ?? 10;
  const nodeR = o.nodeR ?? 0.25;            // world radius of an agent node
  const clearR = o.clearR ?? 1.55;          // reactor rings + node + gap, in world units
  const sideM = o.sideMargin ?? 58;         // px kept free left/right of the orbit (labels)
  const frac = o.sphereFrac ?? 0.43;        // wanted sphere diameter / stage height
  const W = Math.max(120, w || 0), H = Math.max(120, h || 0);
  const halfAvail = (H - padTop - padBottom) / 2;
  // vertical: front node bottom (perspective ~1.18x) must stay inside the stage
  const kV = (halfAvail - 6) / (clearR + nodeR * 1.25) / 1.12;
  const kWanted = (frac * H) / 2;
  // agent nodes: ~11% of the stage height on screen, kept between 44 and 72 px
  const nodePxWanted = Math.max(44, Math.min(72, 0.11 * H));
  // horizontal: the orbit must be at least clearR*1.3 wide in world units; leave room for node + label
  const side = (k) => Math.max(sideM, nodePxWanted * 0.65 + 36);
  let k = Math.max(20, Math.min(kWanted, kV));
  k = Math.max(20, Math.min(k, (W / 2 - side(k)) / (clearR * 1.2)));
  const R = Math.max(clearR * 1.2, Math.min(3.1, (W / 2 - side(k)) / k));
  const sinE = Math.min(0.86, Math.max(0.3, (clearR + 0.05) / R));
  const nodeScale = Math.min(1.15, nodePxWanted / (2 * nodeR * k * 1.15));
  return { k, R, elev: Math.asin(sinE), nodeR, nodeScale, dy: (padTop - padBottom) / 2, sphereFrac: (2 * k) / H };
}

export function rectOverlap(a, b, pad = 0) {
  const x = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) + pad;
  const y = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) + pad;
  return x > 0 && y > 0 ? x * y : 0;
}

/** Number of overlapping pairs among rects {x,y,w,h} (tolerance `tol` px). */
export function countOverlaps(rects, tol = 1) {
  let n = 0;
  for (let i = 0; i < rects.length; i++)
    for (let j = i + 1; j < rects.length; j++)
      if (rectOverlap(rects[i], rects[j], -tol) > 0) n++;
  return n;
}

const SIDES = ["below", "above", "right", "left", "belowRight", "belowLeft", "aboveRight", "aboveLeft"];
function candidate(it, side) {
  const g = 6, r = it.r || 0;
  switch (side) {
    case "above": return { x: it.x - it.w / 2, y: it.y - r - g - it.h };
    case "right": return { x: it.x + r + g, y: it.y - it.h / 2 };
    case "left": return { x: it.x - r - g - it.w, y: it.y - it.h / 2 };
    case "belowRight": return { x: it.x + r * 0.6, y: it.y + r * 0.6 + g };
    case "belowLeft": return { x: it.x - r * 0.6 - it.w, y: it.y + r * 0.6 + g };
    case "aboveRight": return { x: it.x + r * 0.6, y: it.y - r * 0.6 - g - it.h };
    case "aboveLeft": return { x: it.x - r * 0.6 - it.w, y: it.y - r * 0.6 - g - it.h };
    case "below":
    default: return { x: it.x - it.w / 2, y: it.y + r + g };
  }
}

/**
 * Collision-aware label placement. items: [{id, x, y, r, w, h, prio, prev}] (node centre + radius,
 * label size, higher prio placed first, prev = side used last frame for hysteresis).
 * opts: {bounds:{x,y,w,h}, obstacles:[rects], nodes:[{x,y,r}]}. Returns {id: {x, y, side}}.
 * Labels never overlap each other when any free candidate exists; obstacles and node discs are avoided.
 */
export function placeLabels(items, opts = {}) {
  const b = opts.bounds || { x: -1e9, y: -1e9, w: 2e9, h: 2e9 };
  const obstacles = opts.obstacles || [];
  const discs = (opts.nodes || []).map((n) => ({ x: n.x - n.r, y: n.y - n.r, w: 2 * n.r, h: 2 * n.r }));
  const order = items.slice().sort((p, q) => (q.prio || 0) - (p.prio || 0));
  const placed = [];
  const out = {};
  for (const it of order) {
    const sides = it.prev ? [it.prev, ...SIDES.filter((s) => s !== it.prev)] : SIDES;
    let best = null;
    sides.forEach((side, si) => {
      const c = candidate(it, side);
      const rect = { x: c.x, y: c.y, w: it.w, h: it.h };
      let cost = si * 0.01;   // mild preference order; prev side first
      for (const p of placed) cost += rectOverlap(rect, p, 2) * 50;
      for (const o of obstacles) cost += rectOverlap(rect, o) * 2;
      for (const d of discs) cost += rectOverlap(rect, d) * 1.5;
      const ox = Math.max(0, b.x - rect.x) + Math.max(0, rect.x + rect.w - (b.x + b.w));
      const oy = Math.max(0, b.y - rect.y) + Math.max(0, rect.y + rect.h - (b.y + b.h));
      cost += (ox * it.h + oy * it.w) * 8;
      if (!best || cost < best.cost) best = { cost, rect, side };
    });
    // clamp into bounds as a last resort
    const r = best.rect;
    r.x = Math.min(Math.max(r.x, b.x), b.x + b.w - r.w);
    r.y = Math.min(Math.max(r.y, b.y), b.y + b.h - r.h);
    // still overlapping another label? nudge vertically away from it (rare: crowded tiny stages)
    for (let pass = 0; pass < 4; pass++) {
      const hit = placed.find((p) => rectOverlap(r, p, 2) > 0);
      if (!hit) break;
      const down = hit.y + hit.h + 3, up = hit.y - r.h - 3;
      r.y = (Math.abs(down - r.y) <= Math.abs(up - r.y) && down + r.h <= b.y + b.h) || up < b.y ? down : up;
    }
    placed.push(r);
    out[it.id] = { x: r.x, y: r.y, side: best.side };
  }
  return out;
}
