# apps/windows-cc/broker_live.py
"""Live broker adapter slot (Phase 3) — OFF by default and fail-closed.

Standing rule: no live order without a typed "R4 CONFIRM" by the operator in the Jarvis window.
Gates, all required, checked in this order on every single order:
  1. live_trading_enabled is true in config/cc_settings.json (config-file only; the UI,
     the local API and agents cannot switch it on);
  2. Emergency STOP is not active;
  3. the call came from the in-app bridge (origin == "ui"), never the HTTP API or an agent;
  4. the operator typed exactly "R4 CONFIRM" for this order;
  5. a broker adapter is implemented and its key is in Credential Manager.
No adapter is implemented in this build (Sahi or any other), so step 5 always refuses and
nothing is ever sent to a broker. The v7 bundle's browser-DOM order injection was rejected.
"""
from __future__ import annotations

CONFIRM_PHRASE = "R4 CONFIRM"
BROKERS = {
    "sahi": {"label": "Sahi", "keys": ("JARVIS_BROKER_SAHI_API_KEY", "JARVIS_BROKER_SAHI_API_SECRET"), "adapter": None},
    "other": {"label": "Other broker", "keys": ("JARVIS_BROKER_OTHER_API_KEY", "JARVIS_BROKER_OTHER_API_SECRET"), "adapter": None},
}


def status(settings: dict, key_present=lambda name: False) -> dict:
    rows = []
    for bid, b in BROKERS.items():
        rows.append({"id": bid, "label": b["label"], "keys": {k: bool(key_present(k)) for k in b["keys"]},
                     "adapter": "implemented" if b["adapter"] else "not implemented"})
    return {"live_enabled": bool(settings.get("live_trading_enabled") is True), "brokers": rows,
            "confirm_phrase": CONFIRM_PHRASE}


def place_live_order(order: dict, *, settings: dict, halted: bool, origin: str, typed: str,
                     broker: str = "sahi", key_present=lambda name: False) -> dict:
    if settings.get("live_trading_enabled") is not True:
        return {"ok": False, "gate": 1, "error": "Live trading is OFF (config-file setting live_trading_enabled=false). "
                                                  "Paper mode only."}
    if halted:
        return {"ok": False, "gate": 2, "error": "Emergency STOP is active."}
    if origin != "ui":
        return {"ok": False, "gate": 3, "error": "Live orders can only be placed from the Jarvis window."}
    if str(typed or "").strip() != CONFIRM_PHRASE:
        return {"ok": False, "gate": 4, "error": f"Type {CONFIRM_PHRASE} to confirm this live order (R4)."}
    b = BROKERS.get(broker)
    if not b:
        return {"ok": False, "gate": 5, "error": f"unknown broker {broker}"}
    if not all(key_present(k) for k in b["keys"]):
        return {"ok": False, "gate": 5, "error": f"{b['label']} API key/secret not set in Credential Manager."}
    if not b["adapter"]:
        return {"ok": False, "gate": 5, "error": f"No live adapter for {b['label']} in this build — nothing was sent."}
    return {"ok": False, "gate": 5, "error": "adapter refused"}  # pragma: no cover — no adapter exists
