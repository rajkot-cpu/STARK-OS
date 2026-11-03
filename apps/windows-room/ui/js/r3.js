// apps/windows-room/ui/js/r3.js — R3 confirm. Title and body are fixed strings from app.js.
export function confirmR3({ title, body }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "r3-overlay";
    const card = document.createElement("div");
    card.className = "r3-card";
    const h = document.createElement("h2");
    h.textContent = "R3 // " + (title || "Confirm");
    const p = document.createElement("p");
    p.textContent = body || "";
    const row = document.createElement("div");
    row.className = "r3-row";
    const ok = document.createElement("button");
    ok.type = "button";
    ok.textContent = "Confirm";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cancel";
    cancel.textContent = "Cancel";
    ok.onclick = () => { overlay.remove(); resolve(true); };
    cancel.onclick = () => { overlay.remove(); resolve(false); };
    row.append(ok, cancel);
    card.append(h, p, row);
    overlay.append(card);
    document.body.appendChild(overlay);
  });
}
