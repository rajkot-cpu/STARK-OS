// apps/windows-cc/ui/js/icons3d.js — tiny Three.js meshes per nav button
import * as THREE from "../vendor/three.module.js";

const MOTIF = {
  home: "octa",
  core: "sphere",
  agents: "boxes",
  tasks: "torus",
  calendar: "cylinder",
  memory: "icosa",
  conversations: "cone",
  knowledge: "tetra",
  skills: "torusKnot",
  workflows: "ring",
};

function makeGeometry(kind) {
  switch (kind) {
    case "sphere":
      return new THREE.SphereGeometry(0.55, 12, 10);
    case "boxes":
      return new THREE.BoxGeometry(0.7, 0.7, 0.7);
    case "torus":
      return new THREE.TorusGeometry(0.4, 0.16, 8, 16);
    case "cylinder":
      return new THREE.CylinderGeometry(0.35, 0.35, 0.7, 10);
    case "icosa":
      return new THREE.IcosahedronGeometry(0.55, 0);
    case "cone":
      return new THREE.ConeGeometry(0.45, 0.75, 10);
    case "tetra":
      return new THREE.TetrahedronGeometry(0.65);
    case "torusKnot":
      return new THREE.TorusKnotGeometry(0.3, 0.1, 40, 8);
    case "ring":
      return new THREE.TorusGeometry(0.45, 0.12, 8, 20);
    case "octa":
    default:
      return new THREE.OctahedronGeometry(0.55);
  }
}

function mountOne(button) {
  const route = button.dataset.route || "home";
  if (button.querySelector("canvas.nav-icon")) return;

  const canvas = document.createElement("canvas");
  canvas.className = "nav-icon";
  canvas.width = 64;
  canvas.height = 64;
  canvas.setAttribute("aria-hidden", "true");
  button.prepend(canvas);

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "low-power",
    });
  } catch (e) {
    button.classList.add("icon-fallback");
    button.dataset.iconFallback = "1";
    canvas.remove();
    return;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(64, 64, false);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10);
  camera.position.z = 2.4;

  const geo = makeGeometry(MOTIF[route] || "octa");
  const mat = new THREE.MeshBasicMaterial({
    color: 0x38d4ff,
    wireframe: true,
    transparent: true,
    opacity: 0.9,
  });
  const mesh = new THREE.Mesh(geo, mat);
  scene.add(mesh);

  let alive = true;
  const tick = () => {
    if (!alive) return;
    mesh.rotation.x += 0.012;
    mesh.rotation.y += 0.018;
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  };
  tick();

  button._icon3dDispose = () => {
    alive = false;
    geo.dispose();
    mat.dispose();
    renderer.dispose();
  };
}

export function mountNavIcons(navEl) {
  if (!navEl) return;
  const buttons = navEl.querySelectorAll("button[data-route]");
  buttons.forEach((b) => {
    try {
      mountOne(b);
    } catch (e) {
      b.classList.add("icon-fallback");
      b.dataset.iconFallback = "1";
    }
  });
}
