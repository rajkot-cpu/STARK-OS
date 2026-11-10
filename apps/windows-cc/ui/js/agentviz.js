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
