// apps/windows-room/ui/js/bridge.js
// Calls pywebview methods on the windows-cc BridgeApi instance. No canned payloads.
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
    window.addEventListener("pywebviewready", () => finish(apiReady()), { once: true });
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
      if (!ok) return { ok: false, error: "bridge offline" };
    }
    const fn = window.pywebview && window.pywebview.api && window.pywebview.api[method];
    if (typeof fn === "function") {
      return await fn(...args);
    }
  } catch (e) {
    return { ok: false, error: String(e) };
  }
  return { ok: false, error: "bridge offline" };
}
