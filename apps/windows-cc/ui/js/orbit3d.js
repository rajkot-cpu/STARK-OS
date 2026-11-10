// apps/windows-cc/ui/js/orbit3d.js — Stark-style AI Core reactor with every agent as a glossy 3D node
// on its own orbit. State comes from the bridge `agents()` poll (app.js refresh, every 3 s); the pure
// logic (states, badges, easing, pulse, sizing) lives in agentviz.js and is unit-tested.
// Budget: no post-processing; bloom is faked with shared additive sprites; geometries are cached and
// shared; everything created here is disposed in dispose(). 60 fps cap, no rendering while hidden.
import * as THREE from "../vendor/three.module.js";
import { classify, visualFor, Tracker, orbitFor, styleFor, FrameGate, backingFor, cameraDistance,
  badgeFor, damp, corePulse, voicePulse } from "./agentviz.js";

const report = (level, msg) => { try { if (window.__jarvisUiLog) window.__jarvisUiLog(level, msg, "orbit3d"); } catch (_) {} };

const CYAN = 0x38d4ff;
const GOLD = 0xffc35a;
const TRAIL = 32;
const ORBIT_BASE = 2.45;   // agent orbits start outside the reactor's HUD rings (r ~2.05)
const ORBIT_STEP = 0.19;          // points per orbit trail
const PACKETS = 3;         // energy packets per beam

function geometryFor(shape, s) {
  switch (shape) {
    case "box": return new THREE.BoxGeometry(s * 1.3, s * 1.3, s * 1.3);
    case "icosa": return new THREE.IcosahedronGeometry(s, 0);
    case "torus": return new THREE.TorusGeometry(s * 0.75, s * 0.28, 12, 28);
    case "sphere": return new THREE.SphereGeometry(s, 20, 14);
    case "tetra": return new THREE.TetrahedronGeometry(s * 1.15);
    case "octa": return new THREE.OctahedronGeometry(s * 1.05);
    case "cone": return new THREE.ConeGeometry(s * 0.8, s * 1.6, 14);
    case "torusKnot": return new THREE.TorusKnotGeometry(s * 0.6, s * 0.2, 64, 10);
    case "cylinder": return new THREE.CylinderGeometry(s * 0.7, s * 0.7, s * 1.4, 14);
    case "dodeca":
    default: return new THREE.DodecahedronGeometry(s, 0);
  }
}

function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, "rgba(255,255,255,1)");
  r.addColorStop(0.25, "rgba(255,255,255,0.55)");
  r.addColorStop(0.6, "rgba(255,255,255,0.12)");
  r.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = r;
  g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// View-dependent rim glow (fresnel): cyan body fading to a gold edge.
function fresnelMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { cA: { value: new THREE.Color(CYAN) }, cB: { value: new THREE.Color(GOLD) }, uI: { value: 1 } },
    vertexShader: `varying vec3 vN; varying vec3 vV;
      void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform vec3 cA; uniform vec3 cB; uniform float uI; varying vec3 vN; varying vec3 vV;
      void main(){ float f = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 2.4);
        vec3 c = mix(cA, cB, smoothstep(0.35, 1.0, f));
        gl_FragColor = vec4(c * (0.18 + f * 1.7) * uI, clamp(f * 0.95 + 0.05, 0.0, 1.0)); }`,
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
  });
}

const ADD = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };

// Swirling plasma inside the core (cheap trig noise, no textures).
function plasmaMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uI: { value: 1 } },
    vertexShader: `varying vec3 vP; varying vec3 vN; varying vec3 vV;
      void main(){ vP = position; vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform float uTime; uniform float uI; varying vec3 vP; varying vec3 vN; varying vec3 vV;
      float n(vec3 p){ return sin(p.x*3.1+uTime*1.3)*sin(p.y*3.7-uTime*0.9)*sin(p.z*2.9+uTime*1.1); }
      void main(){ vec3 q = vP*2.2; float f = n(q) + 0.55*n(q*2.1+1.7) + 0.3*n(q*4.3-2.1); f = 0.5+0.5*f/1.85;
        float fr = pow(1.0-max(dot(normalize(vN), normalize(vV)),0.0), 1.6);
        vec3 c = mix(vec3(0.05,0.45,0.95), vec3(1.0,0.86,0.55), f*f*f);
        float bands = pow(f, 3.0);
        gl_FragColor = vec4(c*(0.04+bands*0.8+fr*0.55)*uI, 1.0); }`,
    ...ADD,
  });
}

// Soft outer atmosphere (back-side fresnel) so the core looks volumetric.
function atmosphereMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uC: { value: new THREE.Color(CYAN) }, uI: { value: 1 } },
    vertexShader: `varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal);
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec3 uC; uniform float uI; varying vec3 vN;
      void main(){ float f = pow(clamp(0.72 + dot(vN, vec3(0.0,0.0,1.0)), 0.0, 1.0), 3.2);
        gl_FragColor = vec4(uC * f * 0.9 * uI, 1.0); }`,
    side: THREE.BackSide, ...ADD,
  });
}

// Camera-facing corona: animated light rays + glow around the reactor.
function coronaMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uI: { value: 1 }, cA: { value: new THREE.Color(CYAN) }, cB: { value: new THREE.Color(0xfff1c8) } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float uTime; uniform float uI; uniform vec3 cA; uniform vec3 cB; varying vec2 vUv;
      void main(){ vec2 p = vUv*2.0-1.0; float r = length(p); float a = atan(p.y, p.x);
        float rays = (0.5+0.5*sin(a*14.0+uTime*0.6)) * (0.5+0.5*sin(a*23.0-uTime*0.9+r*5.0));
        rays = pow(rays, 2.5) * smoothstep(0.95, 0.22, r) * smoothstep(0.12, 0.3, r);
        float glow = exp(-r*6.5);
        float v = (glow*0.32 + rays*0.6) * uI;
        vec3 c = mix(cB, cA, smoothstep(0.08, 0.45, r));
        gl_FragColor = vec4(c * v, 1.0); }`,
    side: THREE.DoubleSide, ...ADD,
  });
}

// Energy particles spiralling into the core; positions computed on the GPU from per-point seeds.
function streamMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uFlow: { value: 0 }, uI: { value: 1 }, uPR: { value: 1 }, uSize: { value: 40 },
      cA: { value: new THREE.Color(CYAN) }, cB: { value: new THREE.Color(GOLD) } },
    vertexShader: `uniform float uFlow; uniform float uPR; uniform float uSize; attribute vec4 aSeed;
      varying float vA; varying float vL;
      void main(){ float life = fract(aSeed.w + uFlow * aSeed.z);
        float r = mix(4.8, 0.5, pow(life, 0.85)); float ang = aSeed.x + life * 2.4;
        vec3 p = vec3(cos(ang)*r, aSeed.y*(1.0-life)*(1.0-life), sin(ang)*r);
        vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv;
        gl_PointSize = uSize * uPR * (0.5 + life*1.1) / max(0.5, -mv.z);
        vA = smoothstep(0.0, 0.2, life) * (1.0 - smoothstep(0.88, 1.0, life)); vL = life; }`,
    fragmentShader: `uniform float uI; uniform vec3 cA; uniform vec3 cB; varying float vA; varying float vL;
      void main(){ float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.0, d);
        gl_FragColor = vec4(mix(cB, cA, smoothstep(0.0, 0.7, vL)) * a * a * vA * uI, 1.0); }`,
    ...ADD,
  });
}

// Floor disc: reflection pool, concentric rings drifting outwards and a radar sweep.
function floorMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uI: { value: 1 }, uC: { value: new THREE.Color(CYAN) } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float uTime; uniform float uI; uniform vec3 uC; varying vec2 vUv;
      void main(){ vec2 p = vUv*2.0-1.0; float r = length(p); float a = atan(p.y, p.x);
        float rings = pow(0.5+0.5*cos(r*46.0 - uTime*0.9), 28.0);
        float sweep = pow(max(0.0, cos(a - uTime*0.45)), 36.0);
        float spokes = pow(0.5+0.5*cos(a*24.0), 60.0) * smoothstep(0.35, 0.9, r);
        float fall = smoothstep(1.0, 0.25, r);
        float v = (rings*0.32 + sweep*0.28 + spokes*0.12) * fall + exp(-r*r*10.0)*0.45;
        gl_FragColor = vec4(uC * v * uI, 1.0); }`,
    side: THREE.DoubleSide, ...ADD,
  });
}

const NOOP = { update() {}, setHealth() {}, setVoice() {}, select() {}, selected() { return null; }, dispose() {}, ok: false };

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{labels?: HTMLElement|null, host?: HTMLElement|null, compact?: boolean,
 *          onSelect?: (id: string) => void, onLost?: () => void}} opts
 */
export function mountAgentOrbit(canvas, opts = {}) {
  if (!canvas) return NOOP;
  // Size comes from the PARENT's layout box (opts.host, default parentElement), never from the canvas:
  // three.js writes canvas.width = cssSize * devicePixelRatio, so reading the canvas back made the
  // Home core grow 25% per frame on a 125% screen (33,554,432 px, blank core, ~2 GB, window closed).
  // CSS keeps the canvas absolutely positioned at 100% of the host so it can never resize the host.
  const host = opts.host || canvas.parentElement;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  } catch (e) {
    report("error", `WebGL init failed for #${canvas.id}: ${e && e.message ? e.message : e}`);
    return NOOP;
  }
  canvas.addEventListener("webglcontextlost", (ev) => {
    ev.preventDefault();
    report("error", `WebGL context lost on #${canvas.id}`);
    if (opts.onLost) opts.onLost();
  });
  canvas.addEventListener("webglcontextrestored", () => report("info", `WebGL context restored on #${canvas.id}`));

  const compact = !!opts.compact;
  const labelHost = opts.labels || null;
  // Opaque deep-navy clear: the additive glow layers write alpha, which on a transparent canvas
  // showed as dark boxes. The stage CSS backgrounds use the same colour (#02080e).
  renderer.setClearColor(0x02080e, 1);

  const owned = new Set();            // every geometry / material / texture we create
  const own = (x) => { owned.add(x); return x; };
  const scene = new THREE.Scene();
  const FOV = 38;
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
  const camBase = { y: 2.0, z: 9 };
  const LOOK = new THREE.Vector3(0, -0.4, 0);
  camera.position.set(0, camBase.y, camBase.z);
  camera.lookAt(LOOK);

  // Lights only for the glossy agent nodes (the core is all unlit/additive).
  scene.add(new THREE.AmbientLight(0x9fdcff, 0.55));
  const coreLight = new THREE.PointLight(CYAN, 22, 11, 1.4);
  scene.add(coreLight);
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(3, 5, 6);
  scene.add(key);

  const glowTex = own(glowTexture());
  const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };
  const sprite = (color, opacity) => new THREE.Sprite(own(new THREE.SpriteMaterial({ map: glowTex, color, opacity, ...additive })));

  // ---------------- AI Core reactor (hero) ----------------
  // Layers, inside out: white-hot energy sphere, animated plasma, fresnel rim, back-side atmosphere,
  // wire shell, 3 gyroscope rings, 4 camera-facing segmented HUD rings with ticks, a ray corona
  // billboard, layered additive glow sprites, energy streams spiralling in, and a floor glow disc.
  const K = 1;                                        // reactor scale (world units)
  const coreGroup = new THREE.Group();
  scene.add(coreGroup);
  const uTime = { value: 0 };
  const energyMat = own(new THREE.MeshBasicMaterial({ color: 0xeaffff }));
  const energy = new THREE.Mesh(own(new THREE.SphereGeometry(0.24 * K, 32, 24)), energyMat);
  coreGroup.add(energy);
  const plasmaMat = own(plasmaMaterial(uTime));
  const plasma = new THREE.Mesh(own(new THREE.SphereGeometry(0.68 * K, 48, 32)), plasmaMat);
  coreGroup.add(plasma);
  const rimMat = own(fresnelMaterial());
  const rim = new THREE.Mesh(own(new THREE.SphereGeometry(0.92 * K, 64, 40)), rimMat);
  coreGroup.add(rim);
  const atmoMat = own(atmosphereMaterial());
  const atmo = new THREE.Mesh(own(new THREE.SphereGeometry(1.32 * K, 48, 32)), atmoMat);
  coreGroup.add(atmo);
  const shellMat = own(new THREE.MeshBasicMaterial({ color: CYAN, wireframe: true, ...additive, opacity: 0.14 }));
  const shell = new THREE.Mesh(own(new THREE.IcosahedronGeometry(1.08 * K, 2)), shellMat);
  coreGroup.add(shell);
  const ringDefs = [
    { r: 1.18, tube: 0.014, color: CYAN, tilt: [Math.PI / 2.3, 0, 0], spin: [0, 0, 0.55], op: 0.8 },
    { r: 1.26, tube: 0.009, color: GOLD, tilt: [Math.PI / 2.9, 0.5, 0], spin: [0, 0, -0.38], op: 0.6 },
    { r: 1.12, tube: 0.011, color: CYAN, tilt: [0.3, 0, 0.6], spin: [0.25, 0.7, 0], op: 0.55 },
  ];
  const rings = ringDefs.map((d) => {
    const m = new THREE.Mesh(own(new THREE.TorusGeometry(d.r * K, d.tube, 8, 160)),
      own(new THREE.MeshBasicMaterial({ color: d.color, ...additive, opacity: d.op })));
    m.rotation.set(...d.tilt);
    m.userData = d;
    coreGroup.add(m);
    return m;
  });

  // Camera-facing HUD rings: segmented arcs + tick marks, counter-rotating.
  const hud = new THREE.Group();
  coreGroup.add(hud);
  const hudRings = [];
  const arcRing = (r, w, arcs, color, op) => {
    const g = new THREE.Group();
    const mat = own(new THREE.MeshBasicMaterial({ color, ...additive, opacity: op, side: THREE.DoubleSide }));
    arcs.forEach(([a0, len]) => g.add(new THREE.Mesh(own(new THREE.RingGeometry(r - w / 2, r + w / 2, 48, 1, a0, len)), mat)));
    g.userData.mat = mat; g.userData.op = op;
    return g;
  };
  const tickRing = (r, n, len, wid, color, op, every = 0) => {
    const mat = own(new THREE.MeshBasicMaterial({ color, ...additive, opacity: op, side: THREE.DoubleSide }));
    const im = new THREE.InstancedMesh(own(new THREE.PlaneGeometry(wid, len)), mat, n);
    const m = new THREE.Matrix4(); const qq = new THREE.Quaternion(); const ax = new THREE.Vector3(0, 0, 1);
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      const big = every && i % every === 0 ? 1.9 : 1;
      qq.setFromAxisAngle(ax, a - Math.PI / 2);
      m.compose(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0), qq, new THREE.Vector3(1, big, 1));
      im.setMatrixAt(i, m);
    }
    const g = new THREE.Group(); g.add(im); g.userData.mat = mat; g.userData.op = op; g.userData.im = im;
    return g;
  };
  const seg = (n, gapFrac) => Array.from({ length: n }, (_, i) => [(i / n) * Math.PI * 2, (Math.PI * 2 / n) * (1 - gapFrac)]);
  [
    { g: arcRing(0.8 * K, 0.11, seg(10, 0.28), GOLD, 0.5), spin: -0.5, tilt: 0 },
    { g: tickRing(1.02 * K, 60, 0.06, 0.01, CYAN, 0.6, 5), spin: 0.4, tilt: 0 },
    { g: arcRing(1.46 * K, 0.035, seg(12, 0.22), CYAN, 0.85), spin: 0.32, tilt: 0 },
    { g: tickRing(1.6 * K, 96, 0.07, 0.012, GOLD, 0.75, 8), spin: -0.18, tilt: 0.1 },
    { g: arcRing(1.76 * K, 0.06, [[0.2, 1.6], [2.2, 0.5], [3.1, 1.9], [5.3, 0.6]], CYAN, 0.55), spin: 0.12, tilt: -0.08 },
    { g: tickRing(1.95 * K, 180, 0.045, 0.008, CYAN, 0.45, 5), spin: -0.07, tilt: 0.16 },
    { g: arcRing(2.04 * K, 0.012, seg(3, 0.5), GOLD, 0.6), spin: 0.22, tilt: 0.16 },
  ].forEach((d) => { d.g.rotation.x = d.tilt; d.g.userData.spin = d.spin; hud.add(d.g); hudRings.push(d.g); });

  const coronaMat = own(coronaMaterial(uTime));
  const corona = new THREE.Mesh(own(new THREE.PlaneGeometry(7.5 * K, 7.5 * K)), coronaMat);
  coreGroup.add(corona);
  const haloOuter = sprite(CYAN, 0.35);
  haloOuter.scale.setScalar(6.2 * K);
  coreGroup.add(haloOuter);
  const haloMid = sprite(0x9ff0ff, 0.2);
  haloMid.scale.setScalar(2.6 * K);
  coreGroup.add(haloMid);
  const haloInner = sprite(GOLD, 0.45);
  haloInner.scale.setScalar(1.05 * K);
  coreGroup.add(haloInner);

  // Energy streams: particles spiralling into the core along 6 arms (animated on the GPU).
  const NS = compact ? 420 : 700;
  const sPos = new Float32Array(NS * 3);
  const sSeed = new Float32Array(NS * 4);
  for (let i = 0; i < NS; i++) {
    const arm = i % 6;
    const onArm = Math.random() < 0.72;
    sSeed[i * 4] = onArm ? (arm / 6) * Math.PI * 2 + (Math.random() - 0.5) * 0.25 : Math.random() * Math.PI * 2;
    sSeed[i * 4 + 1] = (Math.random() - 0.5) * (onArm ? 1.2 : 3.2);
    sSeed[i * 4 + 2] = 0.12 + Math.random() * 0.14;
    sSeed[i * 4 + 3] = Math.random();
  }
  const sGeo = own(new THREE.BufferGeometry());
  sGeo.setAttribute("position", new THREE.BufferAttribute(sPos, 3));
  sGeo.setAttribute("aSeed", new THREE.BufferAttribute(sSeed, 4));
  const streamMat = own(streamMaterial(uTime));
  const streams = new THREE.Points(sGeo, streamMat);
  streams.frustumCulled = false;
  scene.add(streams);

  // Floor: glowing disc with scanning rings + a reflection pool of the core.
  const floorMat = own(floorMaterial(uTime));
  const floor = new THREE.Mesh(own(new THREE.CircleGeometry(5.2, 96)), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -2.35;
  scene.add(floor);
  const pool = new THREE.Mesh(own(new THREE.PlaneGeometry(3.2, 3.2)),
    own(new THREE.MeshBasicMaterial({ map: glowTex, color: 0x6fe6ff, ...additive, opacity: 0.55 })));
  pool.rotation.x = -Math.PI / 2;
  pool.position.y = -2.33;
  scene.add(pool);

  // Ambient dust.
  const NP = compact ? 220 : 380;
  const pPos = new Float32Array(NP * 3);
  for (let i = 0; i < NP; i++) {
    const r = 2.6 + Math.random() * 4.6;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pPos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pPos[i * 3 + 1] = r * Math.cos(ph) * 0.55;
    pPos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
  }
  const pGeo = own(new THREE.BufferGeometry());
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  const particles = new THREE.Points(pGeo, own(new THREE.PointsMaterial({ map: glowTex, color: 0x7fe3ff,
    size: 0.06, sizeAttenuation: true, opacity: 0.45, ...additive })));
  scene.add(particles);

  // ---------------- Agents ----------------
  const geoCache = new Map();
  const sharedGeo = (keyName, make) => { if (!geoCache.has(keyName)) geoCache.set(keyName, own(make())); return geoCache.get(keyName); };
  const nodes = new Map(); // id -> node record
  const tracker = new Tracker();
  const gate = new FrameGate(60);
  let health = 0.5;
  let voiceState = "idle";
  let vAmp = 0, flowRate = 1, flowPhase = 0;
  let selectedId = null;
  let hoverId = null;
  let alive = true;
  let lastT = performance.now();
  const tmp = new THREE.Vector3();
  const tmpColor = new THREE.Color();

  const selMat = own(new THREE.MeshBasicMaterial({ color: GOLD, ...additive, opacity: 0.9 }));
  const selRing = new THREE.Mesh(own(new THREE.TorusGeometry(0.34, 0.008, 6, 64)), selMat);
  selRing.visible = false;
  scene.add(selRing);

  const nodeSize = 0.23;

  function makeNode(agent, i, n) {
    const st = styleFor(agent.id);
    const orbit = orbitFor(i, n, ORBIT_BASE, ORBIT_STEP, 0.55);
    const pivot = new THREE.Group();
    pivot.rotation.set(orbit.tilt, orbit.yaw, 0);
    scene.add(pivot);

    // thin orbit ring + fading trail behind the node
    const ringGeo = sharedGeo(`orbit:${orbit.radius.toFixed(3)}`, () => {
      const pts = [];
      for (let k = 0; k <= 128; k++) {
        const a = (k / 128) * Math.PI * 2;
        pts.push(new THREE.Vector3(Math.cos(a) * orbit.radius, 0, Math.sin(a) * orbit.radius));
      }
      return new THREE.BufferGeometry().setFromPoints(pts);
    });
    const pathMat = own(new THREE.LineBasicMaterial({ color: st.color, ...additive, opacity: 0.1 }));
    pivot.add(new THREE.LineLoop(ringGeo, pathMat));
    const trailGeo = own(new THREE.BufferGeometry());
    trailGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL * 3), 3));
    trailGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(TRAIL * 3), 3));
    const trailMat = own(new THREE.LineBasicMaterial({ vertexColors: true, ...additive, opacity: 1 }));
    const trail = new THREE.Line(trailGeo, trailMat);
    trail.frustumCulled = false;
    pivot.add(trail);

    // glossy emissive body + crisp edges + soft halo + invisible larger hit target
    const geo = sharedGeo(`${st.shape}:${nodeSize}`, () => geometryFor(st.shape, nodeSize));
    const edgesGeo = sharedGeo(`edges:${st.shape}:${nodeSize}`, () => new THREE.EdgesGeometry(geo, 25));
    const hitGeo = sharedGeo(`hit:${nodeSize}`, () => new THREE.SphereGeometry(nodeSize * 2.2, 8, 6));
    const mat = own(new THREE.MeshStandardMaterial({ color: st.color, emissive: st.color, emissiveIntensity: 0.35,
      metalness: 0.35, roughness: 0.22, flatShading: true, transparent: true, opacity: 0.95 }));
    const mesh = new THREE.Mesh(geo, mat);
    const edgeMat = own(new THREE.LineBasicMaterial({ color: st.color, ...additive, opacity: 0.8 }));
    const edges = new THREE.LineSegments(edgesGeo, edgeMat);
    mesh.add(edges);
    const hit = new THREE.Mesh(hitGeo, own(new THREE.MeshBasicMaterial({ visible: false })));
    hit.userData.agentId = agent.id;
    const halo = sprite(st.color, 0.25);
    halo.scale.setScalar(nodeSize * 5);
    const holder = new THREE.Group();
    holder.add(mesh, halo, hit);
    pivot.add(holder);

    // energy beam to the core: faint line + travelling packets
    const beamGeo = own(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]));
    const beamMat = own(new THREE.LineBasicMaterial({ color: st.color, ...additive, opacity: 0 }));
    const beam = new THREE.Line(beamGeo, beamMat);
    beam.frustumCulled = false;
    scene.add(beam);
    const packets = [];
    for (let k = 0; k < PACKETS; k++) {
      const p = sprite(st.color, 0);
      p.scale.setScalar(nodeSize * 1.4);
      p.visible = false;
      scene.add(p);
      packets.push(p);
    }

    let label = null;
    if (labelHost) {
      label = document.createElement("button");
      label.type = "button";
      label.className = "orbit-label";
      label.dataset.orbitAgent = agent.id;
      label.style.setProperty("--c", "#" + st.color.toString(16).padStart(6, "0"));
      label.innerHTML = `<span class="nm"></span><span class="bd"></span>`;
      label.onclick = () => select(agent.id, true);
      label.onmouseenter = () => { hoverId = agent.id; };
      label.onmouseleave = () => { if (hoverId === agent.id) hoverId = null; };
      labelHost.appendChild(label);
    }
    return { id: agent.id, name: agent.name, style: st, orbit, pivot, holder, mesh, mat, edgeMat, halo, hit,
      pathMat, trail, trailGeo, beam, beamMat, packets, label, angle: orbit.phase, state: "idle", badge: "",
      // eased visual values
      cur: { intensity: 0.32, speed: 0.4, scale: 1, beam: 0, color: new THREE.Color(st.color) } };
  }

  function update(agents) {
    const list = Array.isArray(agents) ? agents : [];
    const now = performance.now();
    list.forEach((a, i) => {
      if (!a || !a.id) return;
      let nd = nodes.get(a.id);
      if (!nd) { nd = makeNode(a, i, list.length); nodes.set(a.id, nd); }
      nd.name = String(a.name || a.id).replace(/\s*agent$/i, "");
      nd.state = classify(a);
      tracker.update(a.id, nd.state, now);
    });
  }

  function select(id, fromUser = false) {
    selectedId = id && nodes.has(id) ? id : (id || null);
    if (fromUser && opts.onSelect && selectedId) opts.onSelect(selectedId);
  }

  // Pointer: click selects, move hovers (raycast once per frame), plus gentle parallax.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const par = { x: 0, y: 0, tx: 0, ty: 0 };
  let pointerDirty = false;
  let pointerIn = false;
  const toNdc = (ev) => {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    return true;
  };
  const pick = () => {
    ray.setFromCamera(ndc, camera);
    const targets = [];
    nodes.forEach((nd) => targets.push(nd.hit));
    const h = ray.intersectObjects(targets, false)[0];
    return h ? h.object.userData.agentId : null;
  };
  const onClick = (ev) => { if (toNdc(ev)) { const id = pick(); if (id) select(id, true); } };
  const onMove = (ev) => { if (toNdc(ev)) { pointerDirty = true; pointerIn = true; par.tx = ndc.x; par.ty = ndc.y; } };
  const onLeave = () => { pointerIn = false; hoverId = null; par.tx = 0; par.ty = 0; canvas.style.cursor = "default"; };
  canvas.addEventListener("click", onClick);
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerleave", onLeave);

  let w0 = 0, h0 = 0, pr0 = 0, dirty = true;
  const stats = { cssW: 0, cssH: 0, bw: 0, bh: 0, pr: 0, fits: 0, frames: 0, coreDiamPx: 0, reactorDiamPx: 0 };
  const ro = typeof ResizeObserver === "function" && host ? new ResizeObserver(() => { dirty = true; }) : null;
  if (ro) ro.observe(host);
  try { (window.__orbitStats = window.__orbitStats || {})[canvas.id || "orbit"] = stats; } catch (_) {}   // live, for tests
  function fit() {
    const dpr = window.devicePixelRatio || 1;
    if (!dirty && dpr === pr0) return;
    dirty = false;
    pr0 = dpr;
    const r = host ? host.getBoundingClientRect() : { width: 320, height: 320 };
    const b = backingFor(r.width, r.height, dpr);
    if (b.w === w0 && b.h === h0 && b.pr === stats.pr) return;
    w0 = b.w; h0 = b.h;
    renderer.setPixelRatio(b.pr);
    renderer.setSize(b.w, b.h, false);        // false: CSS (100% of host) owns the on-screen size
    streamMat.uniforms.uPR.value = b.pr * (b.h / 700);
    camera.aspect = b.w / b.h;
    // fit the outer agent orbit (+labels) in both directions
    const outer = ORBIT_BASE + ORBIT_STEP * 7;
    camBase.z = cameraDistance(camera.aspect, FOV, 3.25, outer + 0.55);
    camera.updateProjectionMatrix();
    Object.assign(stats, { cssW: b.w, cssH: b.h, bw: canvas.width, bh: canvas.height, pr: b.pr });
    stats.fits++;
  }
  const projR = (radius) => {
    const c = coreGroup.position.clone().project(camera);
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).multiplyScalar(radius);
    const e = right.add(coreGroup.position).project(camera);
    return Math.hypot((e.x - c.x) * 0.5 * w0, (e.y - c.y) * 0.5 * h0) * 2;
  };
  const visible = () => !document.hidden && canvas.offsetParent !== null;

  function frame(t) {
    const dt = Math.min(0.1, Math.max(0, (t - lastT) / 1000));
    lastT = t;

    // camera drift + parallax
    par.x = damp(par.x, par.tx, 3, dt);
    par.y = damp(par.y, par.ty, 3, dt);
    camera.position.set(Math.sin(t / 9000) * 0.35 + par.x * 0.45,
      camBase.y + Math.cos(t / 11000) * 0.18 + par.y * 0.3, camBase.z);
    camera.lookAt(LOOK);

    if (pointerDirty && pointerIn) {
      pointerDirty = false;
      hoverId = pick();
      canvas.style.cursor = hoverId ? "pointer" : "default";
    }

    let working = 0;
    nodes.forEach((nd) => { if (nd.state === "working" || nd.state === "waiting") working++; });

    // core: idle breathing, stronger/faster heartbeat with working agents, voice reaction
    const pulse = corePulse(working, t);
    const vp = voicePulse(voiceState, t);
    vAmp = damp(vAmp, vp.amp, 10, dt);
    flowRate = damp(flowRate, vp.flow * (1 + working * 0.35), 2, dt);
    const ts = t / 1000;
    uTime.value = ts;
    const spin = 0.3 + health * 0.5 + working * 0.12 + vAmp * 0.4;
    const breathe = 0.5 + 0.5 * Math.sin(ts * 1.1);
    energy.scale.setScalar(pulse.scale * (1 + 0.14 * vAmp));
    energyMat.color.setRGB(0.78 + 0.22 * pulse.beat, 0.96, 1);
    plasma.scale.setScalar(1 + 0.025 * breathe + 0.05 * pulse.beat * pulse.intensity + 0.08 * vAmp);
    plasma.rotation.y += 0.25 * dt;
    plasmaMat.uniforms.uI.value = 0.75 + 0.35 * pulse.intensity + 0.5 * vAmp;
    rim.scale.setScalar(1 + 0.03 * pulse.beat + 0.05 * vAmp);
    rimMat.uniforms.uI.value = 0.7 + 0.5 * pulse.intensity + 0.15 * pulse.beat + 0.4 * vAmp;
    atmo.scale.setScalar(1 + 0.04 * breathe + 0.06 * vAmp);
    atmoMat.uniforms.uI.value = 0.4 + 0.3 * pulse.intensity + 0.15 * breathe + 0.5 * vAmp;
    shell.rotation.y += spin * 0.3 * dt;
    shell.rotation.x -= spin * 0.1 * dt;
    shellMat.opacity = 0.08 + 0.1 * pulse.intensity + 0.1 * vAmp;
    rings.forEach((m) => {
      const s = m.userData.spin;
      m.rotation.x += s[0] * spin * dt;
      m.rotation.y += s[1] * spin * dt;
      m.rotation.z += s[2] * spin * dt;
    });
    hud.quaternion.copy(camera.quaternion);   // reactor face looks at the viewer
    hudRings.forEach((g, i) => {
      g.rotation.z += g.userData.spin * spin * dt;
      const flick = i % 2 ? pulse.beat : breathe;
      g.userData.mat.opacity = g.userData.op * (0.7 + 0.3 * flick) * (0.75 + 0.35 * pulse.intensity + 0.3 * vAmp);
    });
    corona.quaternion.copy(camera.quaternion);
    coronaMat.uniforms.uI.value = 0.6 + 0.35 * pulse.intensity + 0.2 * pulse.beat + 0.7 * vAmp;
    corona.scale.setScalar(1 + 0.04 * breathe + 0.12 * vAmp);
    haloOuter.material.opacity = 0.1 + 0.1 * pulse.intensity + 0.05 * pulse.beat + 0.12 * vAmp;
    haloOuter.scale.setScalar(6.0 + 0.4 * breathe + 0.6 * pulse.beat * pulse.intensity);
    haloMid.material.opacity = 0.1 + 0.1 * pulse.beat * pulse.intensity + 0.15 * vAmp;
    haloInner.material.opacity = 0.3 + 0.3 * pulse.beat * pulse.intensity + 0.25 * vAmp;
    flowPhase += flowRate * dt;
    streamMat.uniforms.uFlow.value = flowPhase;
    streamMat.uniforms.uI.value = 0.55 + 0.3 * pulse.intensity + 0.4 * vAmp + 0.15 * working;
    floorMat.uniforms.uI.value = 0.5 + 0.3 * pulse.intensity + 0.3 * vAmp;
    pool.material.opacity = 0.35 + 0.2 * breathe + 0.25 * vAmp;
    coreLight.intensity = 14 + 16 * pulse.intensity + 10 * vAmp;
    particles.rotation.y += 0.02 * dt;

    // agents
    nodes.forEach((nd) => {
      const flash = tracker.flash(nd.id, t);
      const v = visualFor(nd.state, flash);
      const c = nd.cur;
      const hov = nd.id === hoverId;
      const sel = nd.id === selectedId;
      c.intensity = damp(c.intensity, v.intensity, 5, dt);
      c.speed = damp(c.speed, v.speed, 2.5, dt);
      c.scale = damp(c.scale, v.scale * (hov ? 1.18 : 1) * (sel ? 1.12 : 1), 8, dt);
      c.beam = damp(c.beam, v.beam || flash ? 1 : 0, 4, dt);
      tmpColor.setHex(v.tint ?? nd.style.color);
      c.color.lerp(tmpColor, 1 - Math.exp(-6 * dt));

      nd.angle += c.speed * nd.orbit.dir * dt;
      const r = nd.orbit.radius;
      nd.holder.position.set(Math.cos(nd.angle) * r, 0, Math.sin(nd.angle) * r);
      nd.mesh.rotation.x += (0.4 + c.speed) * dt;
      nd.mesh.rotation.y += (0.6 + c.speed) * dt;
      const pul = v.pulse ? 1 + 0.12 * Math.sin(t / 150) : 1;
      let blink = 1;
      if (flash) blink = 0.6 + 0.4 * Math.abs(Math.sin(t / 90));
      else if (nd.state === "error") blink = 0.65 + 0.35 * Math.abs(Math.sin(t / 400));
      nd.holder.scale.setScalar(c.scale * pul);

      nd.mat.color.copy(c.color);
      nd.mat.emissive.copy(c.color);
      nd.mat.emissiveIntensity = (0.15 + c.intensity * 0.9) * blink + (hov ? 0.3 : 0);
      nd.edgeMat.color.copy(c.color);
      nd.edgeMat.opacity = 0.35 + 0.6 * c.intensity;
      nd.halo.material.color.copy(c.color);
      nd.halo.material.opacity = (0.12 + 0.5 * c.intensity) * blink * pul + (hov ? 0.15 : 0);
      nd.pathMat.color.copy(c.color);
      nd.pathMat.opacity = 0.06 + 0.16 * c.beam + (sel ? 0.12 : 0);

      // trail: fading arc behind the node (in pivot space)
      const tp = nd.trailGeo.attributes.position.array;
      const tc = nd.trailGeo.attributes.color.array;
      const span = 0.75 + c.speed * 0.25;
      for (let k = 0; k < TRAIL; k++) {
        const f = k / (TRAIL - 1);
        const a = nd.angle - nd.orbit.dir * f * span;
        tp[k * 3] = Math.cos(a) * r; tp[k * 3 + 1] = 0; tp[k * 3 + 2] = Math.sin(a) * r;
        const fade = (1 - f) * (1 - f) * (0.25 + 0.75 * c.intensity);
        tc[k * 3] = c.color.r * fade; tc[k * 3 + 1] = c.color.g * fade; tc[k * 3 + 2] = c.color.b * fade;
      }
      nd.trailGeo.attributes.position.needsUpdate = true;
      nd.trailGeo.attributes.color.needsUpdate = true;

      nd.holder.getWorldPosition(tmp);
      if (c.beam > 0.02) {
        const pos = nd.beam.geometry.attributes.position;
        pos.setXYZ(0, tmp.x, tmp.y, tmp.z);
        pos.setXYZ(1, 0, 0, 0);
        pos.needsUpdate = true;
        nd.beamMat.color.copy(c.color);
        nd.beamMat.opacity = (0.25 + 0.2 * Math.abs(Math.sin(t / 220))) * c.beam;
        nd.beam.visible = true;
        nd.packets.forEach((p, k) => {
          const f = ((t / 650) + k / PACKETS) % 1;     // node -> core
          p.position.set(tmp.x * (1 - f), tmp.y * (1 - f), tmp.z * (1 - f));
          p.material.color.copy(c.color);
          p.material.opacity = c.beam * Math.sin(f * Math.PI) * 0.9;
          p.visible = true;
        });
      } else {
        nd.beam.visible = false;
        nd.packets.forEach((p) => { p.visible = false; });
      }
      if (sel) {
        selRing.visible = true;
        selRing.position.copy(tmp);
        selRing.lookAt(camera.position);
        selRing.rotateZ(t / 600);
        selRing.scale.setScalar(c.scale * (1 + 0.06 * Math.sin(t / 200)));
      }
      if (nd.label) {
        const badge = badgeFor(nd.state, flash);
        if (nd.badge !== badge || nd.label.firstChild.textContent !== nd.name) {
          nd.label.firstChild.textContent = nd.name;
          nd.label.lastChild.textContent = badge;
          nd.badge = badge;
        }
        const cls = `orbit-label st-${flash === "done" ? "done" : nd.state}${sel ? " sel" : ""}${hov ? " hov" : ""}`;
        if (nd.label.className !== cls) nd.label.className = cls;
        tmp.project(camera);
        const x = (tmp.x * 0.5 + 0.5) * w0;
        const y = (-tmp.y * 0.5 + 0.5) * h0;
        nd.label.style.transform = `translate(${x.toFixed(1)}px, ${(y + 16).toFixed(1)}px) translateX(-50%)`;
        nd.label.style.zIndex = sel || hov ? "3" : (tmp.z < 0.98 ? "2" : "1");
      }
    });
    if (!selectedId || !nodes.has(selectedId)) selRing.visible = false;
    renderer.render(scene, camera);
    stats.frames++;
    if (stats.frames % 30 === 1) {
      stats.coreDiamPx = Math.round(projR(0.92));
      stats.reactorDiamPx = Math.round(projR(2.05));
      stats.bw = canvas.width; stats.bh = canvas.height;
    }
  }

  function loop() {
    if (!alive) return;
    if (!visible()) {
      // Page hidden or another route showing: no rendering, check again shortly.
      lastT = performance.now();
      setTimeout(loop, 400);
      return;
    }
    requestAnimationFrame((t) => {
      if (!alive) return;
      if (gate.ok(t, visible())) {
        fit();
        frame(t);
      }
      loop();
    });
  }
  loop();

  return {
    ok: true,
    update,
    select: (id) => select(id, false),
    selected: () => selectedId,
    setHealth(n) { health = Math.max(0, Math.min(1, Number(n) || 0)); },
    setVoice(state) { voiceState = state === "speaking" || state === "listening" ? state : "idle"; },
    dispose() {
      alive = false;
      if (ro) ro.disconnect();
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      nodes.forEach((nd) => { if (nd.label) nd.label.remove(); });
      owned.forEach((d) => d.dispose());
      hudRings.forEach((g) => { if (g.userData.im) g.userData.im.dispose(); });
      renderer.dispose();
    },
  };
}
