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
export function orbitFor(i, n) {
  const k = Math.max(1, n);
  return {
    radius: 1.45 + i * 0.22,
    tilt: ((i % 4) - 1.5) * 0.32 + (i % 2 ? 0.15 : -0.15),
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
