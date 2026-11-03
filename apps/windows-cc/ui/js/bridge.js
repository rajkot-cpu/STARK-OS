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
    return { ok: false, error: String(e) };
  }
  return { ok: false, error: "offline" };
}
