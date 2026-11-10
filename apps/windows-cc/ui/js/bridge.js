// apps/windows-cc/ui/js/bridge.js
function apiReady() {
  return !!(window.pywebview && window.pywebview.api);
}

export function whenReady(timeoutMs = 15000) {
  if (apiReady()) return Promise.resolve(true);
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      resolve(ok);
    };
    const onReady = () => finish(apiReady());
    window.addEventListener("pywebviewready", onReady, { once: true });
    const start = Date.now();
    const tick = setInterval(() => {
      if (apiReady()) {
        clearInterval(tick);
        finish(true);
      } else if (Date.now() - start > timeoutMs) {
        clearInterval(tick);
        finish(false);
      }
    }, 100);
  });
}

export async function call(method, ...args) {
  try {
    if (!apiReady()) {
      const ok = await whenReady(8000);
      if (!ok) return { ok: false, error: "offline" };
    }
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api[method] === "function") {
      return await window.pywebview.api[method](...args);
    }
  } catch (e) {
    uiLog("error", `${method} threw: ${e && e.stack ? e.stack : e}`, "bridge.call");
    return { ok: false, error: String(e) };
  }
  return { ok: false, error: "offline" };
}

// Best-effort: send UI errors to logs/ui-errors.log via the Python bridge.
// early-errors.js (classic script, loaded first) owns the listeners and queues messages until the
// bridge is ready, so errors during startup are no longer dropped.
export function uiLog(level, message, source = "ui") {
  try {
    if (typeof window.__jarvisUiLog === "function") { window.__jarvisUiLog(level, message, source); return; }
    if (method_ok("ui_log")) window.pywebview.api.ui_log(level, String(message).slice(0, 2000), source);
  } catch (_) { /* never throw from the logger */ }
}

function method_ok(name) {
  return apiReady() && typeof window.pywebview.api[name] === "function";
}

if (typeof window.__jarvisUiLog !== "function") {
  window.addEventListener("error", (ev) => {
    uiLog("error", `${ev.message} @ ${ev.filename}:${ev.lineno}:${ev.colno} ${ev.error && ev.error.stack ? ev.error.stack : ""}`, "window.onerror");
  });
  window.addEventListener("unhandledrejection", (ev) => {
    const r = ev.reason;
    uiLog("error", `unhandled rejection: ${r && r.stack ? r.stack : r}`, "promise");
  });
}
