// apps/windows-room/ui/js/app.js
// Hybrid voice: voice_turn / chat reply is spoken. The transcript is never spoken.
import { createRoom } from "./scene.js";
import { call, whenReady } from "./bridge.js";
import { confirmR3 } from "./r3.js";

const banner = document.getElementById("banner");
function setBanner(msg, kind = "danger") {
  banner.textContent = msg || "";
  banner.classList.toggle("show", !!msg);
  banner.classList.toggle("danger", !!msg && kind === "danger");
  banner.classList.toggle("info", !!msg && kind === "info");
}

let room;
try {
  room = createRoom(document.getElementById("room"));
  window.jarvisRoom = room;
} catch (e) {
  setBanner("3D init failed: " + (e && e.message ? e.message : e));
  throw e;
}

let muted = false;
let voiceView = { state: "Voice idle", replyText: "", heardText: "", error: "" };

function showVoice(patch) {
  voiceView = Object.assign({}, voiceView, patch);
  room.setVoice(voiceView);
}

async function speakReply(reply) {
  if (reply) await call("speak", reply);
}

async function refreshFast() {
  const [st, met, feed, mem, agents] = await Promise.all([
    call("status"),
    call("metrics"),
    call("feed", 40),
    call("memory"),
    call("agents"),
  ]);
  if (st.ok) {
    room.setStatus(st.data || {}, "");
    muted = !!(st.data && st.data.muted);
    room.setMuteUi(muted);
  } else {
    room.setStatus({}, st.error || "status offline");
  }
  room.setMetrics(met.ok ? met.data : null, met.ok ? "" : (met.error || "metrics offline"));
  room.setFeed(feed.ok ? (feed.data && feed.data.items) : null, feed.ok ? "" : (feed.error || "feed offline"));
  room.setMemory(mem.ok ? mem.data : null, mem.ok ? "" : (mem.error || "memory offline"));
  room.setAgents(agents.ok ? (agents.data && agents.data.agents) : null, agents.ok ? "" : (agents.error || "agents offline"));
}

async function refreshSlow() {
  const [skills, brief, llms] = await Promise.all([
    call("skills"),
    call("brief"),
    call("llms"),
  ]);
  room.setSkills(skills.ok ? (skills.data && skills.data.skills) : null, skills.ok ? "" : (skills.error || "skills offline"));
  room.setBrief(brief.ok ? (brief.data && brief.data.text) : "", brief.ok ? "" : (brief.error || "brief offline"));
  room.setLlms(llms.ok ? (llms.data && llms.data.providers) : null, llms.ok ? "" : (llms.error || "llm probe failed"));
}

async function refreshAll() {
  await refreshFast();
  await refreshSlow();
}

async function talk() {
  showVoice({ state: "Listening…", error: "", replyText: "" });
  setBanner("");
  const r = await call("voice_turn", 6);
  if (!r.ok) {
    showVoice({ state: "Voice idle", error: r.error || "Could not hear you", heardText: r.text || "" });
    setBanner(r.error || "Could not hear you");
    return;
  }
  showVoice({
    state: "Voice idle",
    heardText: r.text || "",
    replyText: r.reply || "",
    error: "",
  });
  await speakReply(r.reply);
}

async function sendChat(text) {
  const prompt = (text || "").trim();
  if (!prompt) return;
  showVoice({ state: "Thinking…", error: "", replyText: "" });
  const r = await call("chat", prompt);
  if (!r.ok) {
    showVoice({ state: "Voice idle", error: r.error || "chat failed" });
    setBanner(r.error || "chat failed");
    return;
  }
  const reply = (r.data && r.data.reply) || "";
  showVoice({ state: "Voice idle", replyText: reply, heardText: "", error: "" });
  await speakReply(reply);
}

const handlers = {
  async sessionStart() {
    const r = await call("session_start");
    setBanner(r.ok ? "Session started" : (r.error || "session failed"), r.ok ? "info" : "danger");
    await refreshFast();
  },
  async workdayDry() {
    const r = await call("dry_run_workday");
    setBanner(r.ok ? "Dry-run workday complete" : (r.error || "dry-run failed"), r.ok ? "info" : "danger");
    await refreshFast();
  },
  async workdayReal() {
    const ok = await confirmR3({
      title: "Start Workday",
      body: "This runs the real workday and may launch allowlisted apps. Continue?",
    });
    if (!ok) {
      setBanner("Start Workday cancelled", "info");
      return;
    }
    const r = await call("start_workday", true);
    setBanner(r.ok ? "Workday started" : (r.error || "workday failed"), r.ok ? "info" : "danger");
    await refreshFast();
  },
  async toggleMute() {
    const want = !muted;
    const r = await call("mute", want);
    if (r.ok) {
      muted = !!(r.data && r.data.muted);
      setBanner("");
    } else {
      setBanner(r.error || "mute failed");
    }
    room.setMuteUi(muted);
    await refreshFast();
  },
  async talk() { await talk(); },
  async sendChat(_name, text) { await sendChat(text); },
  async probeLlms() {
    room.setLlms(null, "probing");
    const r = await call("llms");
    room.setLlms(r.ok ? (r.data && r.data.providers) : null, r.ok ? "" : (r.error || "llm probe failed"));
  },
  async agentStart(_name, id) {
    const r = await call("agent_start", id);
    if (!r.ok) setBanner(r.error || "agent start failed");
    const agents = await call("agents");
    room.setAgents(agents.ok ? agents.data.agents : null, agents.ok ? "" : (agents.error || "agents offline"));
  },
  async agentStop(_name, id) {
    const r = await call("agent_stop", id);
    if (!r.ok) setBanner(r.error || "agent stop failed");
    const agents = await call("agents");
    room.setAgents(agents.ok ? agents.data.agents : null, agents.ok ? "" : (agents.error || "agents offline"));
  },
};

let busy = false;
room.onAction(async (name, payload) => {
  const fn = handlers[name];
  if (!fn || busy) {
    if (name === "toggleMute") room.setMuteUi(muted);
    return;
  }
  busy = true;
  try {
    await fn(name, payload);
  } catch (e) {
    setBanner(String(e));
  } finally {
    busy = false;
  }
});

async function boot() {
  const ok = await whenReady(15000);
  if (!ok) {
    setBanner("Bridge offline — open this UI from JarvisRoom (pywebview)");
    room.setStatus({}, "bridge offline");
    room.setMetrics(null, "bridge offline");
    room.setFeed(null, "bridge offline");
    room.setMemory(null, "bridge offline");
    room.setAgents(null, "bridge offline");
    room.setSkills(null, "bridge offline");
    room.setBrief("", "bridge offline");
    room.setLlms(null, "bridge offline");
    return;
  }
  setBanner("");
  await refreshAll();
  setInterval(() => { refreshFast().catch((e) => setBanner(String(e))); }, 8000);
}

boot().catch((e) => setBanner(String(e)));
