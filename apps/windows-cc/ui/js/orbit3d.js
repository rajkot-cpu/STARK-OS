// apps/windows-cc/ui/js/orbit3d.js — the AI Core with every agent as a 3D node on its own orbit.
// State comes from the bridge `agents()` poll (app.js refresh, every 3 s); logic lives in agentviz.js.
import * as THREE from "../vendor/three.module.js";
import { classify, visualFor, Tracker, orbitFor, styleFor, FrameGate } from "./agentviz.js";

function geometryFor(shape, s) {
  switch (shape) {
    case "box": return new THREE.BoxGeometry(s * 1.3, s * 1.3, s * 1.3);
    case "icosa": return new THREE.IcosahedronGeometry(s, 0);
    case "torus": return new THREE.TorusGeometry(s * 0.75, s * 0.28, 8, 18);
    case "sphere": return new THREE.SphereGeometry(s, 12, 10);
    case "tetra": return new THREE.TetrahedronGeometry(s * 1.15);
    case "octa": return new THREE.OctahedronGeometry(s * 1.05);
    case "cone": return new THREE.ConeGeometry(s * 0.8, s * 1.6, 10);
    case "torusKnot": return new THREE.TorusKnotGeometry(s * 0.6, s * 0.2, 48, 8);
    case "cylinder": return new THREE.CylinderGeometry(s * 0.7, s * 0.7, s * 1.4, 10);
    case "dodeca":
    default: return new THREE.DodecahedronGeometry(s, 0);
  }
}

const NOOP = { update() {}, setHealth() {}, select() {}, selected() { return null; }, dispose() {}, ok: false };

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{labels?: HTMLElement|null, compact?: boolean, onSelect?: (id: string) => void}} opts
 */
export function mountAgentOrbit(canvas, opts = {}) {
  if (!canvas) return NOOP;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  } catch (e) {
    return NOOP;
  }
  const compact = !!opts.compact;
  const labelHost = opts.labels || null;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.set(0, 2.2, compact ? 8.6 : 8.2);
  camera.lookAt(0, 0, 0);

  // --- AI Core ---
  const coreMat = new THREE.MeshBasicMaterial({ color: 0x38d4ff, wireframe: true, transparent: true, opacity: 0.75 });
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.85, 24, 18), coreMat);
  scene.add(core);
  const coreGlowMat = new THREE.MeshBasicMaterial({ color: 0x38d4ff, transparent: true, opacity: 0.08,
    blending: THREE.AdditiveBlending, depthWrite: false });
  const coreGlow = new THREE.Mesh(new THREE.SphereGeometry(0.7, 16, 12), coreGlowMat);
  scene.add(coreGlow);
  const ringMat = new THREE.MeshBasicMaterial({ color: 0x3dff9a, wireframe: true, transparent: true, opacity: 0.35 });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.08, 0.025, 6, 48), ringMat);
  ring.rotation.x = Math.PI / 2.4;
  scene.add(ring);

  const nodes = new Map(); // id -> node record
  const tracker = new Tracker();
  const gate = new FrameGate(60);
  const disposables = [coreMat, core.geometry, coreGlowMat, coreGlow.geometry, ringMat, ring.geometry];
  let health = 0.5;
  let selectedId = null;
  let alive = true;
  let lastT = performance.now();
  const tmp = new THREE.Vector3();

  const selMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, wireframe: true });
  const selRing = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.015, 6, 32), selMat);
  selRing.visible = false;
  scene.add(selRing);
  disposables.push(selMat, selRing.geometry);

  function makeNode(agent, i, n) {
    const st = styleFor(agent.id);
    const orbit = orbitFor(i, n);
    const pivot = new THREE.Group();
    pivot.rotation.set(orbit.tilt, orbit.yaw, 0);
    scene.add(pivot);

    const pts = [];
    for (let k = 0; k <= 96; k++) {
      const a = (k / 96) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * orbit.radius, 0, Math.sin(a) * orbit.radius));
    }
    const pathGeo = new THREE.BufferGeometry().setFromPoints(pts);
    const pathMat = new THREE.LineBasicMaterial({ color: st.color, transparent: true, opacity: 0.12 });
    pivot.add(new THREE.LineLoop(pathGeo, pathMat));

    const size = compact ? 0.2 : 0.24;
    const geo = geometryFor(st.shape, size);
    const mat = new THREE.MeshBasicMaterial({ color: st.color, wireframe: true, transparent: true, opacity: 0.4 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.userData.agentId = agent.id;
    const glowMat = new THREE.MeshBasicMaterial({ color: st.color, transparent: true, opacity: 0.1,
      blending: THREE.AdditiveBlending, depthWrite: false });
    const glowGeo = new THREE.SphereGeometry(size * 1.5, 12, 10);
    const glow = new THREE.Mesh(glowGeo, glowMat);
    glow.userData.agentId = agent.id;
    const holder = new THREE.Group();
    holder.add(mesh, glow);
    pivot.add(holder);

    const beamGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
    const beamMat = new THREE.LineBasicMaterial({ color: st.color, transparent: true, opacity: 0.0,
      blending: THREE.AdditiveBlending, depthWrite: false });
    const beam = new THREE.Line(beamGeo, beamMat);
    beam.frustumCulled = false;
    scene.add(beam);

    let label = null;
    if (labelHost) {
      label = document.createElement("button");
      label.type = "button";
      label.className = "orbit-label";
      label.dataset.orbitAgent = agent.id;
      label.style.setProperty("--c", "#" + st.color.toString(16).padStart(6, "0"));
      label.onclick = () => select(agent.id, true);
      labelHost.appendChild(label);
    }
    disposables.push(pathGeo, pathMat, geo, mat, glowGeo, glowMat, beamGeo, beamMat);
    return { id: agent.id, name: agent.name, style: st, orbit, pivot, holder, mesh, mat, glow, glowMat,
      pathMat, beam, beamMat, label, angle: orbit.phase, state: "idle", color: new THREE.Color(st.color) };
  }

  function update(agents) {
    const list = Array.isArray(agents) ? agents : [];
    const now = performance.now();
    list.forEach((a, i) => {
      if (!a || !a.id) return;
      let nd = nodes.get(a.id);
      if (!nd) { nd = makeNode(a, i, list.length); nodes.set(a.id, nd); }
      nd.name = a.name || a.id;
      nd.state = classify(a);
      tracker.update(a.id, nd.state, now);
      if (nd.label) {
        const txt = `${nd.name} · ${nd.state}`;
        if (nd.label.textContent !== txt) nd.label.textContent = txt;
        nd.label.className = `orbit-label st-${nd.state}${a.id === selectedId ? " sel" : ""}`;
      }
    });
  }

  function select(id, fromUser = false) {
    selectedId = id && nodes.has(id) ? id : (id || null);
    nodes.forEach((nd) => { if (nd.label) nd.label.classList.toggle("sel", nd.id === selectedId); });
    if (fromUser && opts.onSelect && selectedId) opts.onSelect(selectedId);
  }

  // Click -> pick a node.
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  canvas.addEventListener("click", (ev) => {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return;
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const targets = [];
    nodes.forEach((nd) => targets.push(nd.mesh, nd.glow));
    const hit = ray.intersectObjects(targets, false)[0];
    if (hit) select(hit.object.userData.agentId, true);
  });
  canvas.style.cursor = "pointer";

  let w0 = 0, h0 = 0;
  function fit() {
    const w = canvas.clientWidth || canvas.width || 320;
    const h = canvas.clientHeight || canvas.height || 320;
    if (w === w0 && h === h0) return;
    w0 = w; h0 = h;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // keep the outer orbit in view on narrow canvases
    camera.position.z = (compact ? 8.6 : 8.2) * Math.max(1, 1.15 / camera.aspect);
    camera.updateProjectionMatrix();
  }

  const visible = () => !document.hidden && canvas.offsetParent !== null;

  function frame(t) {
    const dt = Math.min(0.1, (t - lastT) / 1000);
    lastT = t;
    const spin = 0.35 + health * 0.6;
    core.rotation.y += spin * dt;
    core.rotation.x += spin * 0.35 * dt;
    ring.rotation.z += spin * 0.5 * dt;
    coreMat.opacity = 0.4 + health * 0.45;
    ringMat.opacity = 0.2 + health * 0.4;
    let working = 0;
    nodes.forEach((nd) => {
      const flash = tracker.flash(nd.id, t);
      const v = visualFor(nd.state, flash);
      if (nd.state === "working") working++;
      nd.angle += v.speed * nd.orbit.dir * dt;
      nd.holder.position.set(Math.cos(nd.angle) * nd.orbit.radius, 0, Math.sin(nd.angle) * nd.orbit.radius);
      nd.mesh.rotation.x += (0.4 + v.speed) * dt;
      nd.mesh.rotation.y += (0.6 + v.speed) * dt;
      const pulse = v.pulse ? 1 + 0.18 * Math.sin(t / 140) : 1;
      let blink = 1;
      if (flash) blink = 0.55 + 0.45 * Math.abs(Math.sin(t / 90));
      else if (nd.state === "error") blink = 0.6 + 0.4 * Math.abs(Math.sin(t / 400));
      const s = v.scale * pulse * (nd.id === selectedId ? 1.15 : 1);
      nd.holder.scale.setScalar(s);
      nd.color.setHex(v.tint ?? nd.style.color);
      nd.mat.color.copy(nd.color);
      nd.glowMat.color.copy(nd.color);
      nd.beamMat.color.copy(nd.color);
      nd.mat.opacity = Math.min(1, v.intensity * blink + 0.05);
      nd.glowMat.opacity = (v.intensity > 0.5 ? 0.35 : 0.06) * blink * (v.pulse ? pulse : 1);
      nd.pathMat.opacity = v.beam ? 0.3 : 0.1;
      nd.holder.getWorldPosition(tmp);
      if (v.beam || flash) {
        const pos = nd.beam.geometry.attributes.position;
        pos.setXYZ(0, tmp.x, tmp.y, tmp.z);
        pos.setXYZ(1, 0, 0, 0);
        pos.needsUpdate = true;
        nd.beamMat.opacity = (0.35 + 0.35 * Math.abs(Math.sin(t / 180))) * (flash ? 1 : v.intensity);
        nd.beam.visible = true;
      } else {
        nd.beam.visible = false;
      }
      if (nd.id === selectedId) {
        selRing.visible = true;
        selRing.position.copy(tmp);
        selRing.lookAt(camera.position);
      }
      if (nd.label) {
        tmp.project(camera);
        const x = (tmp.x * 0.5 + 0.5) * w0;
        const y = (-tmp.y * 0.5 + 0.5) * h0;
        nd.label.style.transform = `translate(${x.toFixed(1)}px, ${(y + 14).toFixed(1)}px) translateX(-50%)`;
        nd.label.style.zIndex = tmp.z < 0.98 ? "2" : "1";
      }
    });
    if (!selectedId || !nodes.has(selectedId)) selRing.visible = false;
    coreGlowMat.opacity = 0.06 + Math.min(0.3, working * 0.08) * (0.7 + 0.3 * Math.sin(t / 200));
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
      nodes.forEach((nd) => { if (nd.label) nd.label.remove(); });
      disposables.forEach((d) => d.dispose());
      renderer.dispose();
    },
  };
}
