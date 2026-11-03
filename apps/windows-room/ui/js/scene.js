// apps/windows-room/ui/js/scene.js — Three.js workshop room (desk + floating holo plates)
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/CSS2DRenderer.js";

const CYAN = 0x3ff0ff, GOLD = 0xffc94a;

export function buildRoom(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05080d);
  scene.fog = new THREE.Fog(0x05080d, 14, 40);

  const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 100);
  camera.position.set(0, 4.2, 9.5);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(innerWidth, innerHeight);
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);

  const labels = new CSS2DRenderer();
  labels.setSize(innerWidth, innerHeight);
  Object.assign(labels.domElement.style, { position: "absolute", top: "0", pointerEvents: "none" });
  container.appendChild(labels.domElement);

  const controls = new OrbitControls(camera, labels.domElement);
  labels.domElement.style.pointerEvents = "auto";
  controls.target.set(0, 1.6, 0);
  controls.enableDamping = true;
  controls.minDistance = 4; controls.maxDistance = 18;
  controls.maxPolarAngle = Math.PI * 0.49;

  // lights
  scene.add(new THREE.AmbientLight(0x223344, 0.8));
  const key = new THREE.SpotLight(0xbfefff, 60, 30, Math.PI / 5, 0.4);
  key.position.set(0, 9, 3); key.castShadow = true; scene.add(key);
  const rim = new THREE.PointLight(CYAN, 25, 14); rim.position.set(0, 2.2, 1); scene.add(rim);
  const warm = new THREE.PointLight(GOLD, 12, 12); warm.position.set(-5, 3, -3); scene.add(warm);

  // floor + grid
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40),
    new THREE.MeshStandardMaterial({ color: 0x0a0f16, metalness: 0.6, roughness: 0.35 }));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  const grid = new THREE.GridHelper(40, 80, CYAN, 0x0c3440);
  grid.material.transparent = true; grid.material.opacity = 0.25; grid.position.y = 0.01; scene.add(grid);

  // walls with emissive strips
  const wallMat = new THREE.MeshStandardMaterial({ color: 0x0c1219, metalness: 0.4, roughness: 0.7 });
  const back = new THREE.Mesh(new THREE.BoxGeometry(24, 8, 0.3), wallMat); back.position.set(0, 4, -8); scene.add(back);
  for (const x of [-12, 12]) {
    const side = new THREE.Mesh(new THREE.BoxGeometry(0.3, 8, 16), wallMat); side.position.set(x, 4, 0); scene.add(side);
  }
  const stripMat = new THREE.MeshBasicMaterial({ color: CYAN });
  for (let i = -5; i <= 5; i++) {
    const s = new THREE.Mesh(new THREE.BoxGeometry(0.06, 6, 0.05), stripMat);
    s.position.set(i * 2, 4, -7.83); scene.add(s);
  }
  const goldStrip = new THREE.Mesh(new THREE.BoxGeometry(24, 0.05, 0.05), new THREE.MeshBasicMaterial({ color: GOLD }));
  goldStrip.position.set(0, 0.6, -7.83); scene.add(goldStrip);

  // workshop desk
  const deskMat = new THREE.MeshStandardMaterial({ color: 0x1a222c, metalness: 0.8, roughness: 0.3 });
  const top = new THREE.Mesh(new THREE.BoxGeometry(5.5, 0.15, 2.2), deskMat);
  top.position.set(0, 1.05, 0); top.castShadow = true; scene.add(top);
  for (const [x, z] of [[-2.5, -0.9], [2.5, -0.9], [-2.5, 0.9], [2.5, 0.9]]) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.12, 1, 0.12), deskMat);
    leg.position.set(x, 0.5, z); scene.add(leg);
  }
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(top.geometry), new THREE.LineBasicMaterial({ color: CYAN }));
  edge.position.copy(top.position); scene.add(edge);

  // holo table emitter + spinning core
  const emitter = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.8, 0.06, 48),
    new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.6 }));
  emitter.position.set(0, 1.16, 0); scene.add(emitter);
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.05, 1.6, 48, 1, true),
    new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }));
  beam.position.set(0, 1.95, 0); scene.add(beam);
  const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.45, 1),
    new THREE.MeshBasicMaterial({ color: CYAN, wireframe: true }));
  core.position.set(0, 2.3, 0); scene.add(core);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.015, 8, 96), new THREE.MeshBasicMaterial({ color: GOLD }));
  ring.position.copy(core.position); ring.rotation.x = Math.PI / 2; scene.add(ring);

  // plates (CSS2D) at 3D anchors with holo frames
  const anchors = {
    status: new THREE.Vector3(-4.6, 3.1, -1.5),
    voice: new THREE.Vector3(0, 4.4, -2.5),
    agents: new THREE.Vector3(4.6, 3.1, -1.5),
    feed: new THREE.Vector3(0, 1.2, 2.6),
  };
  const plates = {};
  for (const [name, pos] of Object.entries(anchors)) {
    const tpl = document.getElementById(`tpl-${name}`);
    const el = tpl.content.firstElementChild.cloneNode(true);
    const obj = new CSS2DObject(el);
    obj.position.copy(pos);
    scene.add(obj);
    const frame = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.8),
      new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.05, side: THREE.DoubleSide, depthWrite: false }));
    frame.position.copy(pos); frame.lookAt(0, pos.y, 8); scene.add(frame);
    plates[name] = { el, obj, frame, base: pos.y };
  }

  let pulse = 0; // voice activity → core intensity
  const clock = new THREE.Clock();
  function animate() {
    const t = clock.getElapsedTime();
    core.rotation.y = t * (0.6 + pulse * 3);
    core.rotation.x = t * 0.3;
    core.scale.setScalar(1 + Math.sin(t * 3) * 0.04 + pulse * 0.25);
    ring.rotation.z = t * 0.8;
    beam.material.opacity = 0.06 + 0.03 * Math.sin(t * 2) + pulse * 0.1;
    Object.values(plates).forEach((p, i) => {
      const y = p.base + Math.sin(t * 0.9 + i) * 0.06;
      p.obj.position.y = y; p.frame.position.y = y;
    });
    controls.update();
    renderer.render(scene, camera);
    labels.render(scene, camera);
    requestAnimationFrame(animate);
  }
  animate();

  addEventListener("resize", () => {
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight); labels.setSize(innerWidth, innerHeight);
  });

  return { plates, setPulse: (v) => (pulse = v) };
}
