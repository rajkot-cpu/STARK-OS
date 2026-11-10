// apps/windows-cc/ui/js/orbit3d.js — Stark-style AI Core reactor with every agent as a glossy 3D node
// on its own orbit. State comes from the bridge `agents()` poll (app.js refresh, every 3 s); the pure
// logic (states, badges, easing, pulse, sizing) lives in agentviz.js and is unit-tested.
// Budget: no post-processing; bloom is faked with shared additive sprites; geometries are cached and
// shared; everything created here is disposed in dispose(). 60 fps cap, no rendering while hidden.
import * as THREE from "../vendor/three.module.js";
import { classify, visualFor, Tracker, orbitFor, styleFor, FrameGate, canvasCssSize,
  badgeFor, damp, corePulse } from "./agentviz.js";

const report = (level, msg) => { try { if (window.__jarvisUiLog) window.__jarvisUiLog(level, msg, "orbit3d"); } catch (_) {} };

const CYAN = 0x38d4ff;
const GOLD = 0xffc35a;
const TRAIL = 28;          // points per orbit trail
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

const NOOP = { update() {}, setHealth() {}, select() {}, selected() { return null; }, dispose() {}, ok: false };

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{labels?: HTMLElement|null, compact?: boolean, fluid?: boolean,
 *          onSelect?: (id: string) => void, onLost?: () => void}} opts
 */
export function mountAgentOrbit(canvas, opts = {}) {
  if (!canvas) return NOOP;
  // A canvas with no CSS size is laid out at its width/height attributes. three.js setSize() writes
  // those as cssSize * devicePixelRatio, so on a 125% screen reading clientWidth back made the Home
  // core grow 25% per frame (to 33,554,432 px: blank core, ~2 GB WebView, window closed).
  // Fixed-size canvases (opts.fluid false) are pinned to their attribute size in CSS px once.
  let fixed = null;
  if (!opts.fluid) {
    fixed = { w: Number(canvas.getAttribute("width")) || 320, h: Number(canvas.getAttribute("height")) || 320 };
    canvas.style.width = fixed.w + "px";
    canvas.style.height = fixed.h + "px";
  }
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
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);

  const owned = new Set();            // every geometry / material / texture we create
  const own = (x) => { owned.add(x); return x; };
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  const camBase = { y: 2.2, z: compact ? 7.6 : 8.2 };
  camera.position.set(0, camBase.y, camBase.z);
  camera.lookAt(0, 0, 0);

  // Lights only for the glossy agent nodes (the core is all unlit/additive).
  scene.add(new THREE.AmbientLight(0x9fdcff, 0.55));
  const coreLight = new THREE.PointLight(CYAN, 18, 9, 1.6);
  scene.add(coreLight);
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(3, 5, 6);
  scene.add(key);

  const glowTex = own(glowTexture());
  const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false };
  const sprite = (color, opacity) => new THREE.Sprite(own(new THREE.SpriteMaterial({ map: glowTex, color, opacity, ...additive })));

  // ---------------- AI Core reactor ----------------
  const coreGroup = new THREE.Group();
  scene.add(coreGroup);
  const energyMat = own(new THREE.MeshBasicMaterial({ color: 0xd9fbff }));
  const energy = new THREE.Mesh(own(new THREE.SphereGeometry(0.3, 32, 24)), energyMat);
  coreGroup.add(energy);
  const rimMat = own(fresnelMaterial());
  const rim = new THREE.Mesh(own(new THREE.SphereGeometry(0.6, 48, 32)), rimMat);
  coreGroup.add(rim);
  const shellMat = own(new THREE.MeshBasicMaterial({ color: CYAN, wireframe: true, ...additive, opacity: 0.2 }));
  const shell = new THREE.Mesh(own(new THREE.IcosahedronGeometry(0.88, 1)), shellMat);
  coreGroup.add(shell);
  const ringDefs = [
    { r: 1.05, tube: 0.012, color: CYAN, tilt: [Math.PI / 2.3, 0, 0], spin: [0, 0, 0.55], op: 0.75 },
    { r: 1.22, tube: 0.008, color: GOLD, tilt: [Math.PI / 2.9, 0.5, 0], spin: [0, 0, -0.38], op: 0.55 },
    { r: 0.78, tube: 0.01, color: CYAN, tilt: [0.3, 0, 0.6], spin: [0.25, 0.7, 0], op: 0.6 },
  ];
  const rings = ringDefs.map((d) => {
    const m = new THREE.Mesh(own(new THREE.TorusGeometry(d.r, d.tube, 6, 128)),
      own(new THREE.MeshBasicMaterial({ color: d.color, ...additive, opacity: d.op })));
    m.rotation.set(...d.tilt);
    m.userData = d;
    coreGroup.add(m);
    return m;
  });
  // Arc-reactor segments around the core (one instanced draw call).
  const SEG = 14;
  const segMat = own(new THREE.MeshBasicMaterial({ color: GOLD, ...additive, opacity: 0.85 }));
  const segs = new THREE.InstancedMesh(own(new THREE.BoxGeometry(0.11, 0.035, 0.025)), segMat, SEG);
  const m4 = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  for (let i = 0; i < SEG; i++) {
    const a = (i / SEG) * Math.PI * 2;
    q.setFromAxisAngle(new THREE.Vector3(0, 0, 1), a + Math.PI / 2);
    m4.compose(new THREE.Vector3(Math.cos(a) * 0.7, Math.sin(a) * 0.7, 0), q, new THREE.Vector3(1, 1, 1));
    segs.setMatrixAt(i, m4);
  }
  const segPivot = new THREE.Group();
  segPivot.rotation.x = Math.PI / 2.3;
  segPivot.add(segs);
  coreGroup.add(segPivot);
  const haloOuter = sprite(CYAN, 0.35);
  haloOuter.scale.setScalar(3.4);
  coreGroup.add(haloOuter);
  const haloInner = sprite(GOLD, 0.45);
  haloInner.scale.setScalar(1.3);
  coreGroup.add(haloInner);

  // Subtle particle field.
  const NP = compact ? 220 : 420;
  const pPos = new Float32Array(NP * 3);
  for (let i = 0; i < NP; i++) {
    const r = 2.2 + Math.random() * 4.2;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pPos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pPos[i * 3 + 1] = r * Math.cos(ph) * 0.55;
    pPos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
  }
  const pGeo = own(new THREE.BufferGeometry());
  pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
  const particles = new THREE.Points(pGeo, own(new THREE.PointsMaterial({ map: glowTex, color: 0x7fe3ff,
    size: compact ? 0.07 : 0.06, sizeAttenuation: true, opacity: 0.5, ...additive })));
  scene.add(particles);

  // ---------------- Agents ----------------
  const geoCache = new Map();
  const sharedGeo = (keyName, make) => { if (!geoCache.has(keyName)) geoCache.set(keyName, own(make())); return geoCache.get(keyName); };
  const nodes = new Map(); // id -> node record
  const tracker = new Tracker();
  const gate = new FrameGate(60);
  let health = 0.5;
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

  const nodeSize = compact ? 0.2 : 0.24;

  function makeNode(agent, i, n) {
    const st = styleFor(agent.id);
    const orbit = orbitFor(i, n);
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

  let w0 = 0, h0 = 0;
  function fit() {
    const { w, h } = canvasCssSize(canvas.clientWidth, canvas.clientHeight, fixed);
    if (w === w0 && h === h0) return;
    w0 = w; h0 = h;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // keep the outer orbit in view on narrow canvases
    camBase.z = (compact ? 7.6 : 8.2) * Math.max(1, 1.15 / camera.aspect);
    camera.updateProjectionMatrix();
  }

  const visible = () => !document.hidden && canvas.offsetParent !== null;

  function frame(t) {
    const dt = Math.min(0.1, Math.max(0, (t - lastT) / 1000));
    lastT = t;

    // camera drift + parallax
    par.x = damp(par.x, par.tx, 3, dt);
    par.y = damp(par.y, par.ty, 3, dt);
    camera.position.set(Math.sin(t / 9000) * 0.35 + par.x * 0.45,
      camBase.y + Math.cos(t / 11000) * 0.18 + par.y * 0.3, camBase.z);
    camera.lookAt(0, 0, 0);

    if (pointerDirty && pointerIn) {
      pointerDirty = false;
      hoverId = pick();
      canvas.style.cursor = hoverId ? "pointer" : "default";
    }

    let working = 0;
    nodes.forEach((nd) => { if (nd.state === "working" || nd.state === "waiting") working++; });

    // core
    const pulse = corePulse(working, t);
    const spin = 0.3 + health * 0.5 + working * 0.12;
    energy.scale.setScalar(pulse.scale);
    energyMat.color.setRGB(0.75 + 0.25 * pulse.beat, 0.95, 1);
    rim.scale.setScalar(1 + 0.03 * pulse.beat);
    rimMat.uniforms.uI.value = 0.65 + 0.5 * pulse.intensity + 0.15 * pulse.beat;
    shell.rotation.y += spin * 0.35 * dt;
    shell.rotation.x -= spin * 0.12 * dt;
    shellMat.opacity = 0.12 + 0.12 * pulse.intensity;
    rings.forEach((m) => {
      const s = m.userData.spin;
      m.rotation.x += s[0] * spin * dt;
      m.rotation.y += s[1] * spin * dt;
      m.rotation.z += s[2] * spin * dt;
    });
    segs.rotation.z -= spin * 0.6 * dt;
    segMat.opacity = 0.55 + 0.4 * pulse.beat * pulse.intensity;
    haloOuter.material.opacity = 0.18 + 0.22 * pulse.intensity + 0.08 * pulse.beat;
    haloOuter.scale.setScalar(3.2 + 0.35 * pulse.beat * pulse.intensity);
    haloInner.material.opacity = 0.3 + 0.35 * pulse.beat * pulse.intensity;
    coreLight.intensity = 12 + 14 * pulse.intensity;
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
    dispose() {
      alive = false;
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      nodes.forEach((nd) => { if (nd.label) nd.label.remove(); });
      owned.forEach((d) => d.dispose());
      segs.dispose();
      renderer.dispose();
    },
  };
}
