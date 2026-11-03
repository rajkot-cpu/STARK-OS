// apps/windows-room/ui/js/scene.js — workshop bay. Plates show bridge data only.
import * as THREE from "../vendor/three.module.min.js";
import { CSS2DRenderer, CSS2DObject } from "../vendor/CSS2DRenderer.js";
import { OrbitControls } from "../vendor/OrbitControls.js";

const BG = 0x04070b;
const CYAN = 0x38d4ff;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function plate(title, cls) {
  const root = el("div", "plate " + cls);
  root.append(el("div", "plate-title", title));
  const err = el("div", "plate-error", "");
  return { root, err };
}

export function createRoom(containerEl) {
  const listeners = [];
  const emit = (name, payload) => listeners.forEach((cb) => cb(name, payload));

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BG);
  scene.fog = new THREE.Fog(BG, 14, 42);

  const w = () => containerEl.clientWidth || window.innerWidth;
  const h = () => containerEl.clientHeight || window.innerHeight;
  const camera = new THREE.PerspectiveCamera(48, w() / h(), 0.1, 120);
  camera.position.set(0, 1.6, 30);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w(), h());
  containerEl.appendChild(renderer.domElement);

  const labels = new CSS2DRenderer();
  labels.setSize(w(), h());
  labels.domElement.className = "css2d-layer";
  containerEl.appendChild(labels.domElement);

  const grid = new THREE.GridHelper(40, 40, CYAN, CYAN);
  grid.material.transparent = true;
  grid.material.opacity = 0.07;
  grid.position.y = -2.2;
  scene.add(grid);

  const bay = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.BoxGeometry(32, 26, 18)),
    new THREE.LineBasicMaterial({ color: CYAN, transparent: true, opacity: 0.2 }),
  );
  bay.position.y = 0;
  scene.add(bay);

  const coreMat = new THREE.MeshBasicMaterial({ color: CYAN, wireframe: true });
  const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.7, 1), coreMat);
  core.position.set(0, 0.2, 0);
  scene.add(core);

  const status = plate("J.A.R.V.I.S · STATUS", "status-plate");
  const headline = el("div", "headline", "…");
  const strip = el("div", "strip", "");
  status.root.append(headline, strip, status.err);

  const metrics = plate("SYSTEM", "metrics-plate");
  const gauges = el("div", "gauges");
  gauges.append(el("div", "empty", "…"));
  metrics.root.append(gauges, metrics.err);

  const feed = plate("AUDIT FEED", "feed-plate");
  const feedList = el("div", "scroll");
  feedList.append(el("div", "empty", "…"));
  feed.root.append(feedList, feed.err);

  const memory = plate("MEMORY", "memory-plate");
  const memoryBody = el("div", "meta", "");
  memoryBody.append(el("div", "empty", "…"));
  memory.root.append(memoryBody, memory.err);

  const llms = plate("LLM PROBES", "llm-plate");
  const llmList = el("div", "scroll");
  llmList.append(el("div", "empty", "Not probed yet."));
  const probeBtn = el("button", "btn tiny", "Probe");
  probeBtn.type = "button";
  probeBtn.addEventListener("click", (e) => { e.stopPropagation(); emit("probeLlms"); });
  llms.root.append(llmList, probeBtn, llms.err);

  const agents = plate("AGENTS", "agents-plate");
  const agentList = el("div", "scroll");
  agentList.append(el("div", "empty", "…"));
  agents.root.append(agentList, agents.err);

  const skills = plate("SKILLS", "skills-plate");
  const skillList = el("div", "scroll");
  skillList.append(el("div", "empty", "…"));
  skills.root.append(skillList, skills.err);

  const brief = plate("TODAY'S BRIEF", "brief-plate");
  const briefText = el("div", "scroll empty", "…");
  brief.root.append(briefText, brief.err);

  const voice = plate("VOICE", "voice-plate");
  const voiceState = el("div", "meta", "Voice idle");
  const talk = el("button", "btn filled", "Talk");
  talk.type = "button";
  talk.addEventListener("click", (e) => { e.stopPropagation(); emit("talk"); });
  const reply = el("div", "reply", "");
  const heard = el("div", "heard", "");
  const chatRow = el("div", "chat-row");
  const chatInput = document.createElement("input");
  chatInput.type = "text";
  chatInput.placeholder = "Type to JARVIS";
  chatInput.setAttribute("aria-label", "Message");
  const send = el("button", "btn", "Send");
  send.type = "button";
  const submitChat = (e) => {
    if (e) e.stopPropagation();
    const text = chatInput.value;
    chatInput.value = "";
    emit("sendChat", text);
  };
  send.addEventListener("click", submitChat);
  chatInput.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") {
      e.preventDefault();
      submitChat(e);
    }
  });
  chatRow.append(chatInput, send);
  const muteRow = el("label", "mute-row");
  const muteBox = document.createElement("input");
  muteBox.type = "checkbox";
  muteBox.addEventListener("change", (e) => { e.stopPropagation(); emit("toggleMute"); });
  muteRow.append(muteBox, el("span", null, "MUTE"));
  voice.root.append(voiceState, talk, reply, heard, chatRow, muteRow, voice.err);

  const actions = plate("SESSION", "actions-plate");
  const mk = (label, cls, action) => {
    const b = el("button", "btn " + cls, label);
    b.type = "button";
    b.addEventListener("click", (e) => { e.stopPropagation(); emit(action); });
    actions.root.append(b);
    return b;
  };
  mk("SESSION START", "", "sessionStart");
  mk("DRY-RUN WORKDAY", "", "workdayDry");
  mk("START WORKDAY (R3)", "gold", "workdayReal");
  actions.root.append(actions.err);

  const nodes = [
    status.root, metrics.root, feed.root, memory.root, llms.root,
    agents.root, skills.root, brief.root, voice.root, actions.root,
  ];
  nodes.forEach((node) => {
    node.addEventListener("pointerdown", (e) => e.stopPropagation());
    node.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
  });

  const place = (node, x, y, z) => {
    const obj = new CSS2DObject(node);
    obj.position.set(x, y, z);
    scene.add(obj);
    return obj;
  };
  // Separate in X/Y. CSS2D size is in pixels, so shared columns overlap on screen.
  place(brief.root, -10, 8.2, 2);
  place(status.root, 0, 8.2, 2);
  place(agents.root, 10, 8.2, 2);
  place(metrics.root, -10, 2.4, 2);
  place(memory.root, 0, 2.4, 2);
  place(feed.root, 10, 2.4, 2);
  place(skills.root, -10, -3.4, 2);
  place(llms.root, 0, -3.4, 2);
  place(voice.root, -4.2, -9.2, 2);
  place(actions.root, 4.2, -9.2, 2);

  const controls = new OrbitControls(camera, labels.domElement);
  labels.domElement.style.pointerEvents = "auto";
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.enablePan = false;
  controls.minDistance = 8;
  controls.maxDistance = 48;
  controls.maxPolarAngle = Math.PI * 0.55;
  controls.target.set(0, 0.2, 0);
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.18;
  controls.addEventListener("start", () => { controls.autoRotate = false; });

  function resize() {
    camera.aspect = w() / Math.max(h(), 1);
    camera.updateProjectionMatrix();
    renderer.setSize(w(), h());
    labels.setSize(w(), h());
  }
  window.addEventListener("resize", resize);

  let running = true;
  (function loop() {
    if (!running) return;
    requestAnimationFrame(loop);
    core.rotation.y += 0.004;
    core.rotation.x += 0.0015;
    controls.update();
    renderer.render(scene, camera);
    labels.render(scene, camera);
  })();

  function setErr(slot, message) {
    slot.err.textContent = message || "";
  }

  return {
    setStatus(s = {}, error) {
      setErr(status, error);
      const bad = !!error || s.policy_ok === false;
      headline.textContent = s.system_status || (error ? "STATUS UNAVAILABLE" : "—");
      headline.classList.toggle("quiet", !!s.quiet_hours && !bad);
      headline.classList.toggle("danger", bad);
      strip.replaceChildren();
      strip.append(document.createTextNode("DATE " + (s.today || "—") + " · POLICY "));
      strip.append(el("span", s.policy_ok ? "ok" : "bad", s.policy_ok ? "OK" : "NOT APPROVED"));
      strip.append(document.createTextNode(" · QUIET "));
      strip.append(el("span", s.quiet_hours ? "gold" : "", s.quiet_hours ? "ON" : "OFF"));
      strip.append(document.createTextNode(" · MUTE "));
      strip.append(el("span", s.muted ? "gold" : "", s.muted ? "ON" : "OFF"));
      strip.append(document.createTextNode(" · ROOT " + (s.root || "—")));
      const tone = bad ? 0xff3b30 : (s.quiet_hours ? 0xff9d2e : CYAN);
      coreMat.color.setHex(tone);
    },
    setMetrics(data, error) {
      setErr(metrics, error);
      gauges.replaceChildren();
      if (error || !data) {
        gauges.append(el("div", "empty", "Metrics unavailable."));
        return;
      }
      for (const [label, key] of [["CPU", "cpu_pct"], ["RAM", "ram_pct"], ["DISK", "disk_pct"]]) {
        const n = Number(data[key]);
        const known = Number.isFinite(n);
        const wrap = el("div", "gauge");
        wrap.append(el("div", "gauge-label", label + " " + (known ? n.toFixed(0) + "%" : "—")));
        const track = el("div", "track");
        const fill = el("div", "fill");
        fill.style.width = (known ? Math.max(0, Math.min(100, n)) : 0) + "%";
        track.append(fill);
        wrap.append(track);
        gauges.append(wrap);
      }
    },
    setFeed(items, error) {
      setErr(feed, error);
      feedList.replaceChildren();
      const rows = items || [];
      if (!rows.length) {
        feedList.append(el("div", "empty", error ? "Feed unavailable." : "No audit lines."));
        return;
      }
      rows.slice().reverse().forEach((item) => {
        feedList.append(el("div", "row", feedLine(item)));
      });
    },
    setMemory(data, error) {
      setErr(memory, error);
      memoryBody.replaceChildren();
      if (error || !data) {
        memoryBody.append(el("div", "empty", "Memory index unavailable."));
        return;
      }
      memoryBody.append(el("div", null, "Nodes " + data.nodes + " · edges " + data.edges));
      const sources = data.sources || [];
      memoryBody.append(el("div", sources.length ? null : "empty", sources.length ? sources.join(", ") : "No memory files on disk."));
    },
    setLlms(providers, error) {
      if (error === "probing") {
        setErr(llms, "");
        llmList.replaceChildren(el("div", "empty", "Probing…"));
        return;
      }
      setErr(llms, error);
      llmList.replaceChildren();
      if (error) {
        llmList.append(el("div", "empty", "Probe failed."));
        return;
      }
      if (!providers) {
        llmList.append(el("div", "empty", "Not probed yet."));
        return;
      }
      if (!providers.length) {
        llmList.append(el("div", "empty", "No providers configured."));
        return;
      }
      providers.forEach((p) => {
        const row = el("div", "row");
        row.append(el("span", null, p.name || p.id || "—"));
        row.append(el("span", llmClass(p.state), p.state || "—"));
        if (p.detail) row.append(el("div", "detail", String(p.detail)));
        llmList.append(row);
      });
    },
    setAgents(list, error) {
      setErr(agents, error);
      agentList.replaceChildren();
      const rows = list || [];
      if (!rows.length) {
        agentList.append(el("div", "empty", error ? "Agents unavailable." : "No agents."));
        return;
      }
      rows.forEach((a) => {
        const row = el("div", "row");
        row.append(el("span", null, a.name || a.id || "—"));
        row.append(el("span", a.state === "active" ? "ok" : "muted", a.state || "—"));
        const start = el("button", "btn tiny", "Start");
        const stop = el("button", "btn tiny", "Stop");
        start.type = "button";
        stop.type = "button";
        start.addEventListener("click", (e) => { e.stopPropagation(); emit("agentStart", a.id); });
        stop.addEventListener("click", (e) => { e.stopPropagation(); emit("agentStop", a.id); });
        row.append(start, stop);
        if (a.detail) row.append(el("div", "detail", String(a.detail)));
        agentList.append(row);
      });
    },
    setSkills(list, error) {
      setErr(skills, error);
      skillList.replaceChildren();
      const rows = list || [];
      if (!rows.length) {
        skillList.append(el("div", "empty", error ? "Skills unavailable." : "No skills found."));
        return;
      }
      rows.forEach((s) => {
        const row = el("div", "row");
        row.append(el("strong", null, s.name || "—"));
        row.append(el("span", "muted", s.risk || ""));
        if (s.summary) row.append(el("div", "detail", s.summary));
        skillList.append(row);
      });
    },
    setBrief(text, error) {
      setErr(brief, error);
      const t = (text || "").trim();
      briefText.textContent = error ? "Brief unavailable." : (t || "No brief for today.");
      briefText.classList.toggle("empty", !t || !!error);
    },
    setVoice({ state, replyText, heardText, error }) {
      voiceState.textContent = state || "Voice idle";
      reply.textContent = replyText || "";
      heard.textContent = heardText ? ("Captured: " + heardText) : "";
      setErr(voice, error);
    },
    setMuteUi(muted) { muteBox.checked = !!muted; },
    onAction(cb) { if (typeof cb === "function") listeners.push(cb); },
    dispose() {
      running = false;
      window.removeEventListener("resize", resize);
      controls.dispose();
      renderer.dispose();
    },
  };
}

function feedLine(item) {
  if (!item || typeof item !== "object") return String(item ?? "");
  if (item.raw) return String(item.raw);
  const parts = [item.time || item.t, item.task, item.action || item.msg, item.result].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  try {
    return JSON.stringify(item).slice(0, 180);
  } catch {
    return "—";
  }
}

function llmClass(state) {
  if (state === "connected") return "ok";
  if (state === "auth_error" || state === "network_error") return "bad";
  return "muted";
}
