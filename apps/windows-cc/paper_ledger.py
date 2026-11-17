# apps/windows-cc/paper_ledger.py
"""Paper-trading ledger (Phase 3) at <root>/data/paper.db. No money, no broker, ever.

Adapted from the v7 bundle's trading_terminal_monitor.PaperTradingEngine: idempotent
client_order_id and a fill record per order. Fills use the last price from market_data
(delayed); the fill price and its source time are stored with every order.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_IST = timezone(timedelta(hours=5, minutes=30))
_locks: dict[str, threading.Lock] = {}
START_CASH = 1_000_000.0  # ₹10 lakh virtual


def _now() -> str:
    return datetime.now(_IST).isoformat(timespec="seconds")


class PaperLedger:
    def __init__(self, root: Path | str, path: Path | str | None = None):
        self.path = Path(path) if path else Path(root) / "data" / "paper.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _locks.setdefault(str(self.path), threading.Lock())
        with self._lock, self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS orders(
                id TEXT PRIMARY KEY, client_order_id TEXT UNIQUE NOT NULL, ts TEXT NOT NULL, symbol TEXT NOT NULL,
                side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL, price_time INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '', origin TEXT NOT NULL DEFAULT 'manual', note TEXT NOT NULL DEFAULT '')""")
            c.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)")
            c.execute("INSERT OR IGNORE INTO meta(k, v) VALUES ('start_cash', ?)", (str(START_CASH),))

    def _conn(self):
        c = sqlite3.connect(str(self.path), timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def place(self, symbol: str, side: str, qty: float, price: float, *, price_time: int = 0, source: str = "",
              origin: str = "manual", client_order_id: str = "", note: str = "") -> dict:
        side = str(side or "").upper()
        if side not in ("BUY", "SELL"):
            return {"ok": False, "error": "side must be BUY or SELL"}
        try:
            qty, price = float(qty), float(price)
        except Exception:
            return {"ok": False, "error": "qty/price must be numbers"}
        if not (0 < qty <= 100000) or not (price > 0):
            return {"ok": False, "error": "qty must be 1..100000 and price > 0"}
        coid = str(client_order_id or uuid.uuid4().hex)[:64]
        with self._lock, self._conn() as c:
            dup = c.execute("SELECT * FROM orders WHERE client_order_id=?", (coid,)).fetchone()
            if dup:
                return {"ok": True, "duplicate": True, "data": dict(dup)}
            if side == "SELL":
                pos = self._positions(c).get(symbol, {}).get("qty", 0.0)
                if qty > pos + 1e-9:
                    return {"ok": False, "error": f"paper ledger is long-only: you hold {pos:g} {symbol}"}
            if side == "BUY" and qty * price > self._cash(c) + 1e-6:
                return {"ok": False, "error": "not enough virtual cash"}
            oid = "PAPER-" + uuid.uuid4().hex[:10].upper()
            c.execute("INSERT INTO orders(id, client_order_id, ts, symbol, side, qty, price, price_time, source, origin, note) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (oid, coid, _now(), symbol, side, qty, price, int(price_time), source[:120], origin[:20], note[:200]))
            row = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return {"ok": True, "data": dict(row)}

    def _cash(self, c) -> float:
        start = float(c.execute("SELECT v FROM meta WHERE k='start_cash'").fetchone()[0])
        flow = 0.0
        for r in c.execute("SELECT side, qty, price FROM orders"):
            flow += (-1 if r["side"] == "BUY" else 1) * r["qty"] * r["price"]
        return start + flow

    def _positions(self, c) -> dict:
        pos: dict = {}
        for r in c.execute("SELECT symbol, side, qty, price FROM orders ORDER BY ts, rowid"):
            p = pos.setdefault(r["symbol"], {"qty": 0.0, "cost": 0.0, "realized": 0.0})
            if r["side"] == "BUY":
                p["cost"] += r["qty"] * r["price"]
                p["qty"] += r["qty"]
            else:
                avg = p["cost"] / p["qty"] if p["qty"] else 0.0
                p["realized"] += (r["price"] - avg) * r["qty"]
                p["cost"] -= avg * r["qty"]
                p["qty"] -= r["qty"]
        return pos

    def summary(self, marks: dict | None = None) -> dict:
        marks = marks or {}
        with self._lock, self._conn() as c:
            pos = self._positions(c)
            cash = self._cash(c)
            start = float(c.execute("SELECT v FROM meta WHERE k='start_cash'").fetchone()[0])
            orders = [dict(r) for r in c.execute("SELECT * FROM orders ORDER BY ts DESC, rowid DESC LIMIT 30")]
        rows, mv, unreal, real = [], 0.0, 0.0, 0.0
        for sym, p in pos.items():
            real += p["realized"]
            if p["qty"] <= 1e-9:
                continue
            avg = p["cost"] / p["qty"]
            mark = marks.get(sym)
            u = (mark - avg) * p["qty"] if mark else None
            if mark:
                mv += mark * p["qty"]
                unreal += u
            else:
                mv += p["cost"]
            rows.append({"symbol": sym, "qty": p["qty"], "avg": avg, "mark": mark, "unrealized": u})
        return {"start_cash": start, "cash": cash, "positions": rows, "orders": orders, "market_value": mv,
                "equity": cash + mv, "unrealized": unreal, "realized": real}

    def symbols(self) -> list[str]:
        with self._lock, self._conn() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT symbol FROM orders")]

    def reset(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM orders")
