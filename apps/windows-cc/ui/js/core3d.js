// apps/windows-cc/ui/js/core3d.js — holographic AI Core (replaces 2D sphere.js)
import * as THREE from "../vendor/three.module.js";

export function mountCore(canvas) {
  if (!canvas) {
    return { ok: false, setHealth() {}, dispose() {} };
  }

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "low-power",
    });
  } catch (e) {
    return { ok: false, setHealth() {}, dispose() {} };
  }

  const w = canvas.width || 320;
  const h = canvas.height || 320;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w, h, false);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 50);
  camera.position.z = 3.2;

  const group = new THREE.Group();
  scene.add(group);

  const mat = new THREE.MeshBasicMaterial({
    color: 0x38d4ff,
    wireframe: true,
    transparent: true,
    opacity: 0.75,
  });
  const sphere = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 18), mat);
  group.add(sphere);

  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x3dff9a,
    wireframe: true,
    transparent: true,
    opacity: 0.35,
  });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.25, 0.03, 8, 48), ringMat);
  ring.rotation.x = Math.PI / 2.4;
  group.add(ring);

  let health = 0.5;
  let alive = true;
  const tick = () => {
    if (!alive) return;
    const spin = 0.006 + health * 0.01;
    sphere.rotation.y += spin;
    sphere.rotation.x += spin * 0.35;
    ring.rotation.z += spin * 0.5;
    mat.opacity = 0.45 + health * 0.45;
    ringMat.opacity = 0.2 + health * 0.45;
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  };
  tick();

  return {
    ok: true,
    setHealth(n) {
      health = Math.max(0, Math.min(1, Number(n) || 0));
    },
    dispose() {
      alive = false;
      sphere.geometry.dispose();
      mat.dispose();
      ring.geometry.dispose();
      ringMat.dispose();
      renderer.dispose();
    },
  };
}
