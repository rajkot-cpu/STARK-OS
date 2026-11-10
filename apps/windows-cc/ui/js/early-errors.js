// apps/windows-cc/ui/js/early-errors.js — classic (non-module) script loaded before app.js.
// If any ES module in the app.js graph fails to fetch/parse, NO module code runs (bridge.js included),
// so its error listeners never exist. This file catches those cases and queues messages until the
// pywebview bridge is ready, then writes them to logs/ui-errors.log via ui_log.
(function () {
  var queue = [];
  function ready() { return !!(window.pywebview && window.pywebview.api && typeof window.pywebview.api.ui_log === "function"); }
  function flush() {
    if (!ready()) return;
    while (queue.length) {
      var m = queue.shift();
      try { window.pywebview.api.ui_log(m[0], m[1], m[2]); } catch (_) { /* never throw */ }
    }
  }
  window.__jarvisUiLog = function (level, message, source) {
    queue.push([String(level || "error"), String(message).slice(0, 2000), String(source || "ui")]);
    if (queue.length > 200) queue.shift();
    flush();
  };
  window.addEventListener("pywebviewready", flush);
  var t = setInterval(function () { if (ready()) { flush(); if (!queue.length) clearInterval(t); } }, 500);
  setTimeout(function () { clearInterval(t); }, 60000);

  window.addEventListener("error", function (ev) {
    var el = ev.target;
    if (el && el !== window && (el.src || el.href)) {
      // resource load failure (script/link/img) — does not reach window.onerror otherwise
      window.__jarvisUiLog("error", "resource failed to load: " + (el.src || el.href), "resource");
      return;
    }
    window.__jarvisUiLog("error", ev.message + " @ " + ev.filename + ":" + ev.lineno + ":" + ev.colno + " " +
      (ev.error && ev.error.stack ? ev.error.stack : ""), "window.onerror");
  }, true);
  window.addEventListener("unhandledrejection", function (ev) {
    var r = ev.reason;
    window.__jarvisUiLog("error", "unhandled rejection: " + (r && r.stack ? r.stack : r), "promise");
  });
  // Watchdog: app.js sets window.__jarvisBooted when its module graph actually ran.
  setTimeout(function () {
    if (window.__jarvisBooted) return;
    window.__jarvisUiLog("error", "app.js module never started (an ES module import failed to load or parse)", "boot");
    var b = document.getElementById("banner");
    if (b) b.textContent = "UI failed to start — see logs\\ui-errors.log";
  }, 10000);
})();
