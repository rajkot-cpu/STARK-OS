// apps/windows-cc/ui/js/orbit3d.js — Stark-style AI Core reactor (hero v2) with every agent as a
// glossy 3D node on ONE clean outer orbit. State comes from the bridge `agents()` poll (app.js
// refresh, every 3 s); pure logic (states, badges, easing, pulse, stage plan, label layout) lives in
// agentviz.js and is unit-tested.
// Look: a large energy sphere (white-hot centre, domain-warped simplex plasma, fresnel glass shell
// with a gold accent, back-side atmosphere), soft bloom from additive sprites + an anamorphic streak,
// three thin rings + one subtle tick ring, a faint accretion disc, and agents on an outer ellipse.
// Budget: no post-processing; geometries cached/shared; everything created here is disposed in
// dispose(); 60 fps cap; no rendering while hidden; backing store <= 2048 px.
import * as THREE from "../vendor/three.module.js";
import { classify, visualFor, Tracker, styleFor, FrameGate, backingFor, badgeFor, damp, corePulse,
  voicePulse, stagePlan, ringPhase, placeLabels, countOverlaps } from "./agentviz.js";

const report = (level, msg) => { try { if (window.__jarvisUiLog) window.__jarvisUiLog(level, msg, "orbit3d"); } catch (_) {} };

const CYAN = 0x38d4ff;
const GOLD = 0xffc35a;
const TRAIL = 28;          // points per node trail
const PACKETS = 3;         // energy packets per beam
const FOV = 22;            // narrow lens: mild perspective, the plan math stays accurate
const ORBIT_SPEED = 0.11;  // rad/s, shared outer orbit (slow, elegant)

function geometryFor(shape, s) {
  switch (shape) {
    case "box": return new THREE.BoxGeometry(s * 1.25, s * 1.25, s * 1.25, 1, 1, 1);
    case "icosa": return new THREE.IcosahedronGeometry(s * 1.05, 0);
    case "torus": return new THREE.TorusGeometry(s * 0.72, s * 0.3, 16, 40);
    case "sphere": return new THREE.SphereGeometry(s * 0.95, 28, 20);
    case "tetra": return new THREE.TetrahedronGeometry(s * 1.2);
    case "octa": return new THREE.OctahedronGeometry(s * 1.1);
    case "cone": return new THREE.ConeGeometry(s * 0.8, s * 1.6, 6);
    case "torusKnot": return new THREE.TorusKnotGeometry(s * 0.58, s * 0.2, 96, 12);
    case "cylinder": return new THREE.CylinderGeometry(s * 0.7, s * 0.7, s * 1.4, 18);
    case "dodeca":
    default: return new THREE.DodecahedronGeometry(s, 0);
  }
}

// Soft radial glow (exponential-ish falloff reads like real bloom, no hard edge).
function glowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d");
  const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  [[0, 1], [0.08, 0.82], [0.2, 0.45], [0.38, 0.18], [0.6, 0.06], [0.8, 0.015], [1, 0]]
    .forEach(([o, a]) => r.addColorStop(o, `rgba(255,255,255,${a})`));
  g.fillStyle = r;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// 3D simplex noise — Ian McEwan / Ashima Arts "webgl-noise" (MIT licence), standard formulation.
const NOISE = `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){ float s=0.0, a=0.5; for(int i=0;i<4;i++){ s+=a*snoise(p); p=p*2.03+vec3(1.7,9.2,3.1); a*=0.5; } return s; }
`;
const VS_VIEW = `varying vec3 vP; varying vec3 vN; varying vec3 vV;
  void main(){ vP = position; vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`;
const ADD = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };

// Inner plasma: domain-warped fbm with bright filaments (ridged noise), deep blue -> cyan -> white,
// gold flecks on the hottest ridges; brighter through the middle (more plasma along the view ray).
function plasmaMaterial(uTime, scale = 1, seed = 0) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uI: { value: 1 }, uAmp: { value: 0 }, uS: { value: scale }, uSeed: { value: seed } },
    vertexShader: VS_VIEW,
    fragmentShader: `uniform float uTime; uniform float uI; uniform float uAmp; uniform float uS; uniform float uSeed;
      varying vec3 vP; varying vec3 vN; varying vec3 vV;
      ${NOISE}
      void main(){
        vec3 p = normalize(vP) * uS + uSeed; float t = uTime * (0.16 + 0.25 * uAmp) + uSeed;
        vec3 q = vec3(fbm(p*1.5 + vec3(0.0, 0.0, t)), fbm(p*1.5 + vec3(5.2, 1.3, -t)), fbm(p*1.5 + vec3(-3.1, 7.7, t*0.7)));
        float n = fbm(p*2.3 + q*1.6 + vec3(0.0, t*1.4, 0.0));
        float ridge = pow(1.0 - abs(n), 6.0);
        float mu = max(dot(normalize(vN), normalize(vV)), 0.0);
        float fr = pow(1.0 - mu, 2.2);
        vec3 deep = vec3(0.01, 0.10, 0.30), cy = vec3(0.10, 0.70, 1.00), wh = vec3(0.90, 0.98, 1.00), gd = vec3(1.0, 0.74, 0.32);
        vec3 c = mix(deep, cy, smoothstep(0.0, 0.85, n));
        c = mix(c, wh, ridge * 0.6);
        c += gd * pow(ridge, 2.5) * smoothstep(0.05, 0.5, q.x) * 0.55;
        float body = 0.35 + 0.65 * pow(mu, 0.8);
        vec3 col = c * (0.2 + ridge * 1.05) * body + cy * fr * 0.35;
        gl_FragColor = vec4(col * uI, 1.0); }`,
    ...ADD,
  });
}

// White-hot centre: white at the middle, cyan towards its limb, soft edge.
function hotCoreMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uI: { value: 1 } },
    vertexShader: VS_VIEW,
    fragmentShader: `uniform float uI; varying vec3 vP; varying vec3 vN; varying vec3 vV;
      void main(){ float d = max(dot(normalize(vN), normalize(vV)), 0.0);
        vec3 c = mix(vec3(0.15, 0.65, 1.0), vec3(1.0, 1.0, 0.98), pow(d, 1.6));
        gl_FragColor = vec4(c * pow(d, 1.4) * 0.85 * uI, 1.0); }`,
    ...ADD,
  });
}

// Glass shell: thin fresnel rim (cyan, gold accent on the upper-left), faint holo lines and a slow
// scan band so the sphere reads as an engineered containment field, not a flat disc.
function shellMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uI: { value: 1 } },
    vertexShader: VS_VIEW,
    fragmentShader: `uniform float uTime; uniform float uI; varying vec3 vP; varying vec3 vN; varying vec3 vV;
      void main(){ vec3 n = normalize(vN); float mu = max(dot(n, normalize(vV)), 0.0);
        float fr = pow(1.0 - mu, 3.2);
        float g = smoothstep(0.25, 0.95, dot(n, normalize(vec3(-0.55, 0.78, 0.25))));
        vec3 c = mix(vec3(0.30, 0.86, 1.0), vec3(1.0, 0.76, 0.34), g * 0.9);
        float lines = smoothstep(0.93, 1.0, 0.5 + 0.5 * sin(vP.y * 30.0 - uTime * 0.8)) * 0.18 * (0.25 + fr);
        float band = exp(-pow((vP.y - sin(uTime * 0.3) * 0.85) * 6.0, 2.0)) * 0.22 * (0.3 + fr);
        gl_FragColor = vec4(c * (fr * 1.7 + lines + band) * uI, 1.0); }`,
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
      void main(){ float f = pow(clamp(0.68 + dot(vN, vec3(0.0, 0.0, 1.0)), 0.0, 1.0), 3.0);
        gl_FragColor = vec4(uC * f * 0.75 * uI, 1.0); }`,
    side: THREE.BackSide, ...ADD,
  });
}

// Faint accretion disc in the orbit plane: soft glow + fine rings, gently rotating.
function discMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uI: { value: 1 }, uC: { value: new THREE.Color(CYAN) }, uR: { value: 3 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float uTime; uniform float uI; uniform vec3 uC; uniform float uR; varying vec2 vUv;
      void main(){ vec2 p = (vUv * 2.0 - 1.0) * uR; float r = length(p); float a = atan(p.y, p.x);
        float glow = exp(-pow((r - 1.25) * 1.6, 2.0)) * 0.10;
        float fine = pow(0.5 + 0.5 * cos(r * 34.0), 30.0) * smoothstep(1.1, 1.5, r) * smoothstep(uR, uR * 0.55, r) * 0.05;
        float arc = pow(max(0.0, cos(a * 3.0 - uTime * 0.25)), 10.0) * smoothstep(1.2, 1.7, r) * smoothstep(uR, 1.8, r) * 0.05;
        float edge = smoothstep(uR, uR * 0.85, r);
        gl_FragColor = vec4(uC * (glow + fine + arc) * edge * uI, 1.0); }`,
    side: THREE.DoubleSide, ...ADD,
  });
}

// Energy motes drifting inward in the orbit plane (GPU-animated from per-point seeds).
function streamMaterial(uTime) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime, uFlow: { value: 0 }, uI: { value: 1 }, uPR: { value: 1 }, uSize: { value: 40 }, uR: { value: 3 },
      cA: { value: new THREE.Color(CYAN) }, cB: { value: new THREE.Color(GOLD) } },
    vertexShader: `uniform float uFlow; uniform float uPR; uniform float uSize; uniform float uR; attribute vec4 aSeed;
      varying float vA; varying float vL;
      void main(){ float life = fract(aSeed.w + uFlow * aSeed.z);
        float r = mix(uR * 1.05, 1.05, pow(life, 0.8)); float ang = aSeed.x + life * 1.8;
        vec3 p = vec3(cos(ang) * r, aSeed.y * (1.0 - life), sin(ang) * r);
        vec4 mv = modelViewMatrix * vec4(p, 1.0); gl_Position = projectionMatrix * mv;
        gl_PointSize = uSize * uPR * (0.5 + life * 0.9) / max(0.5, -mv.z);
        vA = smoothstep(0.0, 0.25, life) * (1.0 - smoothstep(0.85, 1.0, life)); vL = life; }`,
    fragmentShader: `uniform float uI; uniform vec3 cA; uniform vec3 cB; varying float vA; varying float vL;
      void main(){ float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.0, d);
        gl_FragColor = vec4(mix(cB, cA, smoothstep(0.0, 0.7, vL)) * a * a * vA * uI, 1.0); }`,
    ...ADD,
  });
}

// Tiny procedural environment for glossy reflections on agent nodes (no network/runtime assets).
function makeEnv(renderer) {
  const pm = new THREE.PMREMGenerator(renderer);
  const env = new THREE.Scene();
  const disposables = [];
  const add = (geo, color, pos, scale) => {
    const mat = new THREE.MeshBasicMaterial({ color, side: THREE.BackSide });
    const m = new THREE.Mesh(geo, mat); m.position.set(...pos); if (scale) m.scale.set(...scale);
    env.add(m); disposables.push(geo, mat);
  };
  add(new THREE.SphereGeometry(10, 24, 16), 0x03101a, [0, 0, 0]);
  const panel = (color, pos, s) => {
    const geo = new THREE.PlaneGeometry(1, 1); const mat = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide });
    const m = new THREE.Mesh(geo, mat); m.position.set(...pos); m.scale.set(...s); m.lookAt(0, 0, 0); env.add(m); disposables.push(geo, mat);
  };
  panel(0xffffff, [3, 6, 4], [5, 2, 1]);
  panel(0x38d4ff, [-6, 1, 2], [3, 6, 1]);
  panel(0xffc35a, [5, -2, -5], [4, 3, 1]);
  panel(0x9ff0ff, [0, 2, -7], [8, 1, 1]);
  const rt = pm.fromScene(env, 0.035);
  disposables.forEach((d) => d.dispose());
  pm.dispose();
  return rt;
}

const NOOP = { update() {}, setHealth() {}, setVoice() {}, select() {}, selected() { return null; }, dispose() {}, ok: false };

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{labels?: HTMLElement|null, host?: HTMLElement|null, compact?: boolean, padTop?: number,
 *          padBottom?: number, obstacles?: () => HTMLElement[],
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
  renderer.setClearColor(0x02080e, 1);   // opaque: additive layers on a transparent canvas showed boxes

  const owned = new Set();
  const own = (x) => { owned.add(x); return x; };
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 200);
  const cam = { d: 12, elev: 0.5 };
  let envRT = null;
  try { envRT = makeEnv(renderer); } catch (e) { report("warn", `env map: ${e && e.message ? e.message : e}`); }

  scene.add(new THREE.AmbientLight(0x9fdcff, 0.35));
  const coreLight = new THREE.PointLight(CYAN, 30, 14, 1.3);
  scene.add(coreLight);
  const key = new THREE.DirectionalLight(0xffffff, 1.4);
  key.position.set(3, 6, 6);
  scene.add(key);
  const rimLight = new THREE.DirectionalLight(GOLD, 0.6);
  rimLight.position.set(-5, 2, -4);
  scene.add(rimLight);

  const glowTex = own(glowTexture());
  const sprite = (color, opacity) => new THREE.Sprite(own(new THREE.SpriteMaterial({ map: glowTex, color, opacity, ...ADD })));

  // ---------------- AI Core reactor ----------------
  const coreGroup = new THREE.Group();
  scene.add(coreGroup);
  const uTime = { value: 0 };
  const hotMat = own(hotCoreMaterial());
  const hot = new THREE.Mesh(own(new THREE.SphereGeometry(0.27, 32, 24)), hotMat);
  coreGroup.add(hot);
  const plasmaMat = own(plasmaMaterial(uTime));
  const plasma = new THREE.Mesh(own(new THREE.SphereGeometry(0.9, 64, 48)), plasmaMat);
  coreGroup.add(plasma);
  // second, smaller plasma layer turning the other way: parallax between the two reads as depth
  const innerMat = own(plasmaMaterial(uTime, 1.7, 11.3));
  const inner = new THREE.Mesh(own(new THREE.SphereGeometry(0.6, 48, 32)), innerMat);
  coreGroup.add(inner);
  const shellMat = own(shellMaterial(uTime));
  const shell = new THREE.Mesh(own(new THREE.SphereGeometry(1.0, 72, 48)), shellMat);
  coreGroup.add(shell);
  const atmoMat = own(atmosphereMaterial());
  const atmo = new THREE.Mesh(own(new THREE.SphereGeometry(1.32, 48, 32)), atmoMat);
  coreGroup.add(atmo);

  // bloom: layered additive sprites + a thin anamorphic streak (film lens look)
  const bloomWide = sprite(CYAN, 0.24); bloomWide.scale.setScalar(5.6); coreGroup.add(bloomWide);
  const bloomMid = sprite(0x9ff0ff, 0.3); bloomMid.scale.setScalar(2.9); coreGroup.add(bloomMid);
  const bloomHot = sprite(0xffffff, 0.45); bloomHot.scale.setScalar(0.7); coreGroup.add(bloomHot);
  const goldKiss = sprite(GOLD, 0.16); goldKiss.scale.setScalar(1.9); goldKiss.position.set(-0.28, 0.3, 0.2); coreGroup.add(goldKiss);
  const streak = sprite(0x8fe8ff, 0.32); streak.scale.set(7.5, 0.09, 1); coreGroup.add(streak);
  const streak2 = sprite(0xffffff, 0.35); streak2.scale.set(2.8, 0.035, 1); coreGroup.add(streak2);

  // rings: 3 main (gold segmented HUD ring, orbit-plane equator ring, tilted gyroscope ring)
  // + 1 subtle tick ring. Thin and slow, clear hierarchy: gold = primary, cyan = secondary.
  const hud = new THREE.Group();            // camera-facing layer
  coreGroup.add(hud);
  const ringMat = (color, op) => own(new THREE.MeshBasicMaterial({ color, ...ADD, opacity: op, side: THREE.DoubleSide }));
  const goldRing = new THREE.Group();
  const goldMat = ringMat(GOLD, 0.75);
  for (let i = 0; i < 6; i++) {
    const a0 = (i / 6) * Math.PI * 2;
    goldRing.add(new THREE.Mesh(own(new THREE.RingGeometry(1.115, 1.135, 64, 1, a0, (Math.PI * 2 / 6) * 0.72)), goldMat));
  }
  const goldDotsMat = ringMat(GOLD, 0.9);
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2 + (Math.PI * 2 / 6) * 0.86;
    const m = new THREE.Mesh(own(new THREE.CircleGeometry(0.016, 10)), goldDotsMat);
    m.position.set(Math.cos(a) * 1.125, Math.sin(a) * 1.125, 0);
    goldRing.add(m);
  }
  hud.add(goldRing);
  const tickMat = ringMat(CYAN, 0.28);
  const NT = 120;
  const ticks = new THREE.InstancedMesh(own(new THREE.PlaneGeometry(0.006, 0.035)), tickMat, NT);
  {
    const m = new THREE.Matrix4(); const qq = new THREE.Quaternion(); const ax = new THREE.Vector3(0, 0, 1);
    for (let i = 0; i < NT; i++) {
      const a = (i / NT) * Math.PI * 2;
      qq.setFromAxisAngle(ax, a - Math.PI / 2);
      m.compose(new THREE.Vector3(Math.cos(a) * 1.24, Math.sin(a) * 1.24, 0), qq, new THREE.Vector3(1, i % 10 === 0 ? 2.2 : 1, 1));
      ticks.setMatrixAt(i, m);
    }
  }
  const tickRing = new THREE.Group(); tickRing.add(ticks); hud.add(tickRing);
  const eqMat = ringMat(CYAN, 0.55);
  const equator = new THREE.Mesh(own(new THREE.TorusGeometry(1.38, 0.006, 6, 200)), eqMat);
  equator.rotation.x = Math.PI / 2;
  coreGroup.add(equator);
  const runners = [0, Math.PI].map((ph) => { const s = sprite(0xbff6ff, 0.9); s.scale.setScalar(0.16); s.userData.ph = ph; coreGroup.add(s); return s; });
  const gyroMat = ringMat(0xbfefff, 0.35);
  // gyroscope: three arcs on a FIXED tilt (never goes edge-on into a hard line across the sphere);
  // spinning the arcs about their own axis gives the motion
  const gyro = new THREE.Group();
  const arcGeo = own(new THREE.TorusGeometry(1.3, 0.005, 6, 120, Math.PI * 0.5));
  for (let i = 0; i < 3; i++) { const m = new THREE.Mesh(arcGeo, gyroMat); m.rotation.z = (i / 3) * Math.PI * 2; gyro.add(m); }
  const gyroPivot = new THREE.Group(); gyroPivot.rotation.order = "ZYX"; gyroPivot.rotation.set(-1.1, 0.0, 0.7); gyroPivot.add(gyro); coreGroup.add(gyroPivot);

  // accretion disc (orbit plane) + inward energy motes + ambient dust
  const discMat = own(discMaterial(uTime));
  const disc = new THREE.Mesh(own(new THREE.PlaneGeometry(2, 2)), discMat);
  disc.rotation.x = -Math.PI / 2;
  scene.add(disc);
  const NS = compact ? 260 : 420;
  const sSeed = new Float32Array(NS * 4);
  for (let i = 0; i < NS; i++) {
    sSeed[i * 4] = Math.random() * Math.PI * 2;
    sSeed[i * 4 + 1] = (Math.random() - 0.5) * 0.5;
    sSeed[i * 4 + 2] = 0.05 + Math.random() * 0.07;
    sSeed[i * 4 + 3] = Math.random();
  }
  const sGeo = own(new THREE.BufferGeometry());
  sGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(NS * 3), 3));
  sGeo.setAttribute("aSeed", new THREE.BufferAttribute(sSeed, 4));
  const streamMat = own(streamMaterial(uTime));
  const streams = new THREE.Points(sGeo, streamMat);
  streams.frustumCulled = false;
  scene.add(streams);
  const NP = compact ? 160 : 260;
  const pPos = new Float32Array(NP * 3);
  for (let i = 0; i < NP; i++) {
    const r = 2.2 + Math.random() * 5;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pPos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pPos[i * 3 + 1] = r * Math.cos(ph) * 0.6;
    pPos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
  }
  const pGeo = own(new THREE.BufferGeometry());
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  const dust = new THREE.Points(pGeo, own(new THREE.PointsMaterial({ map: glowTex, color: 0x7fe3ff,
    size: 0.045, sizeAttenuation: true, opacity: 0.35, ...ADD })));
  scene.add(dust);

  // the shared outer orbit path (rebuilt when the plan's radius changes)
  const orbitMat = own(new THREE.LineBasicMaterial({ color: CYAN, ...ADD, opacity: 0.2 }));
  let orbitLine = null;
  let orbitR = 0;
  function setOrbitRadius(R) {
    if (Math.abs(R - orbitR) < 1e-3) return;
    orbitR = R;
    if (orbitLine) { scene.remove(orbitLine); owned.delete(orbitLine.geometry); orbitLine.geometry.dispose(); }
    const pts = [];
    for (let k = 0; k <= 256; k++) { const a = (k / 256) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * R, 0, Math.sin(a) * R)); }
    orbitLine = new THREE.LineLoop(own(new THREE.BufferGeometry().setFromPoints(pts)), orbitMat);
    scene.add(orbitLine);
    discMat.uniforms.uR.value = R + 0.4;
    disc.scale.setScalar(R + 0.4);
    streamMat.uniforms.uR.value = R;
  }

  // ---------------- Agents ----------------
  const geoCache = new Map();
  const sharedGeo = (keyName, make) => { if (!geoCache.has(keyName)) geoCache.set(keyName, own(make())); return geoCache.get(keyName); };
  const nodes = new Map();
  const order = [];
  const tracker = new Tracker();
  const gate = new FrameGate(60);
  let health = 0.5;
  let voiceState = "idle";
  let vAmp = 0, flowRate = 1, flowPhase = 0, orbitAngle = 0;
  let selectedId = null, hoverId = null;
  let alive = true;
  let lastT = performance.now();
  const tmp = new THREE.Vector3();
  const tmp2 = new THREE.Vector3();
  const tmpColor = new THREE.Color();
  const NODE = 0.25;

  const selMat = own(new THREE.MeshBasicMaterial({ color: GOLD, ...ADD, opacity: 0.9, side: THREE.DoubleSide }));
  const selRing = new THREE.Mesh(own(new THREE.RingGeometry(NODE * 1.75, NODE * 1.83, 64)), selMat);
  selRing.visible = false;
  scene.add(selRing);

  function makeNode(agent) {
    const st = styleFor(agent.id);
    const holder = new THREE.Group();
    scene.add(holder);
    const geo = sharedGeo(`${st.shape}:${NODE}`, () => geometryFor(st.shape, NODE));
    const edgesGeo = sharedGeo(`edges:${st.shape}`, () => new THREE.EdgesGeometry(geo, 30));
    const hitGeo = sharedGeo("hit", () => new THREE.SphereGeometry(NODE * 1.9, 8, 6));
    const mat = own(new THREE.MeshPhysicalMaterial({ color: st.color, emissive: st.color, emissiveIntensity: 0.3,
      metalness: 0.25, roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.06, envMap: envRT ? envRT.texture : null,
      envMapIntensity: 1.3, flatShading: st.shape !== "sphere" && st.shape !== "torus" && st.shape !== "torusKnot" }));
    const mesh = new THREE.Mesh(geo, mat);
    const edgeMat = own(new THREE.LineBasicMaterial({ color: 0xffffff, ...ADD, opacity: 0.5 }));
    if (st.shape !== "sphere" && st.shape !== "torus" && st.shape !== "torusKnot") mesh.add(new THREE.LineSegments(edgesGeo, edgeMat));
    const hit = new THREE.Mesh(hitGeo, own(new THREE.MeshBasicMaterial({ visible: false })));
    hit.userData.agentId = agent.id;
    const halo = sprite(st.color, 0.3);
    halo.scale.setScalar(NODE * 5.5);
    // holo plinth ring in the orbit plane under each node
    const plinthMat = own(new THREE.MeshBasicMaterial({ color: st.color, ...ADD, opacity: 0.55, side: THREE.DoubleSide }));
    const plinth = new THREE.Mesh(sharedGeo("plinth", () => new THREE.RingGeometry(NODE * 1.3, NODE * 1.36, 48)), plinthMat);
    plinth.rotation.x = -Math.PI / 2;
    const body = new THREE.Group();
    body.add(mesh, halo, plinth, hit);
    holder.add(body);

    const trailGeo = own(new THREE.BufferGeometry());
    trailGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL * 3), 3));
    trailGeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(TRAIL * 3), 3));
    const trail = new THREE.Line(trailGeo, own(new THREE.LineBasicMaterial({ vertexColors: true, ...ADD, opacity: 1 })));
    trail.frustumCulled = false;
    scene.add(trail);

    const beamGeo = own(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]));
    const beamMat = own(new THREE.LineBasicMaterial({ color: st.color, ...ADD, opacity: 0 }));
    const beam = new THREE.Line(beamGeo, beamMat);
    beam.frustumCulled = false;
    scene.add(beam);
    const packets = [];
    for (let k = 0; k < PACKETS; k++) {
      const p = sprite(st.color, 0);
      p.scale.setScalar(NODE * 1.3);
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
      label.innerHTML = `<i class="dot"></i><span class="nm"></span><span class="bd"></span>`;
      label.onclick = () => select(agent.id, true);
      label.onmouseenter = () => { hoverId = agent.id; };
      label.onmouseleave = () => { if (hoverId === agent.id) hoverId = null; };
      labelHost.appendChild(label);
    }
    return { id: agent.id, name: agent.name, style: st, holder, body, mesh, mat, edgeMat, halo, plinth, plinthMat, hit,
      trail, trailGeo, beam, beamMat, packets, label, lw: 0, lh: 0, side: null, state: "idle", badge: "", slot: 0,
      cur: { intensity: 0.4, spin: 0.5, scale: 1, beam: 0, color: new THREE.Color(st.color) } };
  }

  function update(agents) {
    const list = Array.isArray(agents) ? agents : [];
    const now = performance.now();
    list.forEach((a) => {
      if (!a || !a.id) return;
      let nd = nodes.get(a.id);
      if (!nd) { nd = makeNode(a); nodes.set(a.id, nd); order.push(a.id); }
      nd.name = String(a.name || a.id).replace(/\s*agent$/i, "");
      nd.state = classify(a);
      tracker.update(a.id, nd.state, now);
    });
    order.forEach((id, i) => { nodes.get(id).slot = ringPhase(i, order.length); });
  }

  function select(id, fromUser = false) {
    selectedId = id && nodes.has(id) ? id : (id || null);
    if (fromUser && opts.onSelect && selectedId) opts.onSelect(selectedId);
  }

  // Pointer: click selects, move hovers (raycast once per frame), gentle parallax.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const par = { x: 0, y: 0, tx: 0, ty: 0 };
  let pointerDirty = false, pointerIn = false;
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
  let plan = stagePlan(320, 320, opts);
  const stats = { cssW: 0, cssH: 0, bw: 0, bh: 0, pr: 0, fits: 0, frames: 0, coreDiamPx: 0, reactorDiamPx: 0,
    sphereFrac: 0, nodeMinPx: 0, nodeMaxPx: 0, labelOverlaps: 0, labels: [] };
  const ro = typeof ResizeObserver === "function" && host ? new ResizeObserver(() => { dirty = true; }) : null;
  if (ro) ro.observe(host);
  try { (window.__orbitStats = window.__orbitStats || {})[canvas.id || "orbit"] = stats; } catch (_) {}
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
    plan = stagePlan(b.w, b.h, opts);
    camera.aspect = b.w / b.h;
    cam.d = b.h / (2 * plan.k * Math.tan((FOV * Math.PI) / 360));
    cam.elev = plan.elev;
    camera.setViewOffset(b.w, b.h, 0, -plan.dy, b.w, b.h);   // core sits a little low, clear of the title
    camera.updateProjectionMatrix();
    setOrbitRadius(plan.R);
    Object.assign(stats, { cssW: b.w, cssH: b.h, bw: canvas.width, bh: canvas.height, pr: b.pr });
    stats.fits++;
  }
  const project = (v) => { tmp2.copy(v).project(camera); return { x: (tmp2.x * 0.5 + 0.5) * w0, y: (-tmp2.y * 0.5 + 0.5) * h0, z: tmp2.z }; };
  const projR = (radius) => {
    const c = project(coreGroup.position);
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).multiplyScalar(radius).add(coreGroup.position);
    const e = project(right);
    return Math.hypot(e.x - c.x, e.y - c.y) * 2;
  };
  const visible = () => !document.hidden && canvas.offsetParent !== null;
  const obstacleRects = () => {
    if (!opts.obstacles) return [];
    const cr = canvas.getBoundingClientRect();
    return opts.obstacles().filter((el) => el && el.offsetParent !== null).map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.left - cr.left - 4, y: r.top - cr.top - 4, w: r.width + 8, h: r.height + 8 };
    });
  };
  let obstacleCache = [], obstacleAge = 0;

  function frame(t) {
    const dt = Math.min(0.1, Math.max(0, (t - lastT) / 1000));
    lastT = t;
    par.x = damp(par.x, par.tx, 2.5, dt);
    par.y = damp(par.y, par.ty, 2.5, dt);
    const sway = Math.sin(t / 14000) * 0.035;
    const e = cam.elev + par.y * 0.03 + Math.cos(t / 17000) * 0.015;
    const yaw = sway + par.x * 0.05;
    camera.position.set(Math.sin(yaw) * Math.cos(e) * cam.d, Math.sin(e) * cam.d, Math.cos(yaw) * Math.cos(e) * cam.d);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();

    if (pointerDirty && pointerIn) {
      pointerDirty = false;
      hoverId = pick();
      canvas.style.cursor = hoverId ? "pointer" : "default";
    }

    let working = 0;
    nodes.forEach((nd) => { if (nd.state === "working" || nd.state === "waiting") working++; });

    const pulse = corePulse(working, t);
    const vp = voicePulse(voiceState, t);
    vAmp = damp(vAmp, vp.amp, 10, dt);
    flowRate = damp(flowRate, vp.flow * (1 + working * 0.35), 2, dt);
    const ts = t / 1000;
    uTime.value = ts;
    const breathe = 0.5 + 0.5 * Math.sin(ts * 0.9);
    const spin = 0.6 + health * 0.4 + working * 0.15 + vAmp * 0.5;
    hot.scale.setScalar(pulse.scale * (1 + 0.16 * vAmp));
    hotMat.uniforms.uI.value = 0.9 + 0.25 * pulse.beat * pulse.intensity + 0.35 * vAmp;
    plasma.rotation.y += 0.06 * spin * dt;
    plasma.scale.setScalar(1 + 0.012 * breathe + 0.03 * pulse.beat * pulse.intensity + 0.05 * vAmp);
    plasmaMat.uniforms.uI.value = 0.85 + 0.3 * pulse.intensity + 0.45 * vAmp;
    plasmaMat.uniforms.uAmp.value = vAmp;
    inner.rotation.y -= 0.11 * spin * dt;
    inner.rotation.x += 0.03 * spin * dt;
    innerMat.uniforms.uI.value = 0.55 + 0.25 * pulse.intensity + 0.4 * vAmp;
    innerMat.uniforms.uAmp.value = vAmp;
    shellMat.uniforms.uI.value = 0.75 + 0.3 * pulse.intensity + 0.1 * pulse.beat + 0.35 * vAmp;
    shell.scale.setScalar(1 + 0.012 * pulse.beat + 0.03 * vAmp);
    atmo.scale.setScalar(1 + 0.03 * breathe + 0.05 * vAmp);
    atmoMat.uniforms.uI.value = 0.45 + 0.25 * pulse.intensity + 0.1 * breathe + 0.45 * vAmp;
    bloomWide.material.opacity = 0.2 + 0.08 * pulse.intensity + 0.05 * breathe + 0.12 * vAmp;
    bloomWide.scale.setScalar(5.4 + 0.3 * breathe + 0.5 * vAmp);
    bloomMid.material.opacity = 0.22 + 0.1 * pulse.beat * pulse.intensity + 0.15 * vAmp;
    bloomHot.material.opacity = 0.36 + 0.16 * pulse.beat * pulse.intensity + 0.25 * vAmp;
    streak.material.opacity = 0.3 + 0.1 * breathe + 0.2 * vAmp;
    streak.scale.x = 7.2 + 0.6 * breathe + 1.2 * vAmp;
    streak2.material.opacity = 0.28 + 0.15 * vAmp;
    hud.quaternion.copy(camera.quaternion);
    goldRing.rotation.z += 0.07 * spin * dt;
    goldMat.opacity = 0.6 + 0.2 * pulse.intensity + 0.15 * vAmp;
    tickRing.rotation.z -= 0.03 * spin * dt;
    tickMat.opacity = 0.2 + 0.1 * pulse.intensity + 0.15 * vAmp;
    equator.rotation.z += 0.05 * spin * dt;
    eqMat.opacity = 0.4 + 0.15 * breathe + 0.2 * vAmp;
    runners.forEach((s) => { const a = s.userData.ph + ts * 0.35 * spin; s.position.set(Math.cos(a) * 1.38, 0, Math.sin(a) * 1.38); });
    gyro.rotation.z += 0.12 * spin * dt;
    flowPhase += flowRate * dt;
    streamMat.uniforms.uFlow.value = flowPhase;
    streamMat.uniforms.uI.value = 0.3 + 0.25 * pulse.intensity + 0.5 * vAmp + 0.12 * working;
    discMat.uniforms.uI.value = 0.7 + 0.3 * pulse.intensity + 0.4 * vAmp;
    coreLight.intensity = 22 + 14 * pulse.intensity + 10 * vAmp;
    dust.rotation.y += 0.012 * dt;

    // agents on the shared outer orbit
    orbitAngle += ORBIT_SPEED * dt;
    const R = plan.R;
    const core = project(coreGroup.position);
    const camDist = camera.position.length();
    const coreRpx = plan.k * 1.05;
    let nMin = Infinity, nMax = 0;
    const items = [];
    const discs = [];
    nodes.forEach((nd) => {
      const flash = tracker.flash(nd.id, t);
      const v = visualFor(nd.state, flash);
      const c = nd.cur;
      const hov = nd.id === hoverId;
      const sel = nd.id === selectedId;
      c.intensity = damp(c.intensity, Math.max(0.42, v.intensity), 5, dt);
      c.spin = damp(c.spin, 0.35 + v.speed * 0.6, 2.5, dt);
      c.scale = damp(c.scale, v.scale * (hov ? 1.15 : 1) * (sel ? 1.1 : 1), 8, dt);
      c.beam = damp(c.beam, v.beam || flash ? 1 : 0, 4, dt);
      tmpColor.setHex(v.tint ?? nd.style.color);
      c.color.lerp(tmpColor, 1 - Math.exp(-6 * dt));

      const a = nd.slot + orbitAngle;
      nd.holder.position.set(Math.cos(a) * R, 0, Math.sin(a) * R);
      // depth compensation: far nodes are not allowed to shrink much (readable at the back)
      const depth = nd.holder.position.distanceTo(camera.position) / camDist;
      const comp = Math.pow(depth, 0.8) * plan.nodeScale;
      nd.mesh.rotation.x += 0.3 * c.spin * dt;
      nd.mesh.rotation.y += 0.7 * c.spin * dt;
      const pul = v.pulse ? 1 + 0.08 * Math.sin(t / 160) : 1;
      let blink = 1;
      if (flash) blink = 0.6 + 0.4 * Math.abs(Math.sin(t / 90));
      else if (nd.state === "error") blink = 0.65 + 0.35 * Math.abs(Math.sin(t / 400));
      nd.body.scale.setScalar(c.scale * pul * comp);
      nd.mat.color.copy(c.color);
      nd.mat.emissive.copy(c.color);
      nd.mat.emissiveIntensity = (0.18 + c.intensity * 0.75) * blink + (hov ? 0.25 : 0);
      nd.edgeMat.opacity = 0.25 + 0.45 * c.intensity;
      nd.halo.material.color.copy(c.color);
      nd.halo.material.opacity = (0.1 + 0.42 * c.intensity) * blink * pul + (hov ? 0.12 : 0);
      nd.plinthMat.color.copy(c.color);
      nd.plinthMat.opacity = 0.1 + 0.18 * c.intensity + 0.4 * c.beam + (sel || hov ? 0.25 : 0);
      nd.plinth.rotation.z += 0.6 * dt;

      const tp = nd.trailGeo.attributes.position.array;
      const tc = nd.trailGeo.attributes.color.array;
      const span = 0.32 + 0.25 * c.intensity;
      for (let k = 0; k < TRAIL; k++) {
        const f = k / (TRAIL - 1);
        const aa = a - f * span;
        tp[k * 3] = Math.cos(aa) * R; tp[k * 3 + 1] = 0; tp[k * 3 + 2] = Math.sin(aa) * R;
        const fade = (1 - f) * (1 - f) * (0.35 + 0.65 * c.intensity);
        tc[k * 3] = c.color.r * fade; tc[k * 3 + 1] = c.color.g * fade; tc[k * 3 + 2] = c.color.b * fade;
      }
      nd.trailGeo.attributes.position.needsUpdate = true;
      nd.trailGeo.attributes.color.needsUpdate = true;

      tmp.copy(nd.holder.position);
      if (c.beam > 0.02) {
        const pos = nd.beam.geometry.attributes.position;
        pos.setXYZ(0, tmp.x, tmp.y, tmp.z);
        pos.setXYZ(1, 0, 0, 0);
        pos.needsUpdate = true;
        nd.beamMat.color.copy(c.color);
        nd.beamMat.opacity = (0.3 + 0.2 * Math.abs(Math.sin(t / 220))) * c.beam;
        nd.beam.visible = true;
        nd.packets.forEach((p, k) => {
          const f = ((t / 700) + k / PACKETS) % 1;
          p.position.set(tmp.x * (1 - f), 0, tmp.z * (1 - f));
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
        selRing.quaternion.copy(camera.quaternion);
        selRing.scale.setScalar(c.scale * comp * (1 + 0.05 * Math.sin(t / 200)));
      }

      const s = project(tmp);
      const rpx = (plan.k * NODE * c.scale * comp) / depth;  // comp includes nodeScale
      nMin = Math.min(nMin, 2 * rpx * 1.15); nMax = Math.max(nMax, 2 * rpx * 1.15);
      discs.push({ x: s.x, y: s.y, r: rpx * 1.1 });
      if (nd.label) {
        const badge = badgeFor(nd.state, flash);
        if (nd.badge !== badge || nd.label.children[1].textContent !== nd.name) {
          nd.label.children[1].textContent = nd.name;
          nd.label.children[2].textContent = badge;
          nd.badge = badge;
          nd.lw = 0;
        }
        const behindCore = tmp.distanceTo(camera.position) > camDist && Math.hypot(s.x - core.x, s.y - core.y) < coreRpx;
        const cls = `orbit-label st-${flash === "done" ? "done" : nd.state}${sel ? " sel" : ""}${hov ? " hov" : ""}${behindCore && !sel && !hov ? " behind" : ""}`;
        if (nd.label.className !== cls) { nd.label.className = cls; nd.lw = 0; }
        if (!nd.lw) { nd.lw = nd.label.offsetWidth || 80; nd.lh = nd.label.offsetHeight || 20; }
        const prio = (sel ? 100 : 0) + (hov ? 50 : 0) + (nd.state !== "idle" ? 20 : 0) + (1 - s.z) * 10;
        items.push({ id: nd.id, x: s.x, y: s.y, r: rpx * 1.1, w: nd.lw, h: nd.lh, prio, prev: nd.side, nd,
          z: sel || hov ? 4 : (s.z < project(coreGroup.position).z ? 3 : 2) });
      }
    });
    if (!selectedId || !nodes.has(selectedId)) selRing.visible = false;

    if (items.length) {
      if (--obstacleAge <= 0) { obstacleCache = obstacleRects(); obstacleAge = 30; }
      const cr = plan.k * 1.02;   // keep labels off the sphere and its gold ring
      const core2 = { x: core.x - cr, y: core.y - cr, w: cr * 2, h: cr * 2 };
      const pos = placeLabels(items, { bounds: { x: 4, y: 4, w: w0 - 8, h: h0 - 8 },
        obstacles: [...obstacleCache, core2], nodes: discs });
      const rects = [];
      items.forEach((it) => {
        const p = pos[it.id];
        it.nd.side = p.side;
        it.nd.label.style.transform = `translate(${p.x.toFixed(1)}px, ${p.y.toFixed(1)}px)`;
        it.nd.label.style.zIndex = String(it.z);
        rects.push({ id: it.id, x: p.x, y: p.y, w: it.w, h: it.h });
      });
      if (stats.frames % 15 === 0) { stats.labels = rects; stats.labelOverlaps = countOverlaps(rects); }
    }
    renderer.render(scene, camera);
    stats.frames++;
    if (stats.frames % 30 === 1) {
      stats.coreDiamPx = Math.round(projR(1.0));
      stats.reactorDiamPx = Math.round(projR(1.38));
      stats.sphereFrac = +(stats.coreDiamPx / Math.max(1, h0)).toFixed(3);
      stats.nodeMinPx = Math.round(nMin === Infinity ? 0 : nMin);
      stats.nodeMaxPx = Math.round(nMax);
      stats.bw = canvas.width; stats.bh = canvas.height;
    }
  }

  function loop() {
    if (!alive) return;
    if (!visible()) {
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
    relayout() { dirty = true; obstacleAge = 0; },
    dispose() {
      alive = false;
      if (ro) ro.disconnect();
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      nodes.forEach((nd) => { if (nd.label) nd.label.remove(); });
      owned.forEach((d) => d.dispose());
      ticks.dispose();
      if (envRT) envRT.dispose();
      renderer.dispose();
    },
  };
}
