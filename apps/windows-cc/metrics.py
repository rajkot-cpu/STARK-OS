# apps/windows-cc/metrics.py
from __future__ import annotations

import os
import time

import psutil

# last (monotonic time, total bytes) sample for the network rate; empty until the first call
_NET: dict = {}
_GB = 1024 ** 3


def _net_rate() -> float | None:
    """Bytes per second (sent + received) since the previous call; None on the first call."""
    c = psutil.net_io_counters()
    now = time.monotonic()
    total = float(c.bytes_sent + c.bytes_recv)
    prev = dict(_NET)
    _NET.update(t=now, b=total)
    if not prev or now <= prev["t"]:
        return None
    return max(0.0, (total - prev["b"]) / (now - prev["t"]))


def snapshot() -> dict:
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/")
    vm = psutil.virtual_memory()
    try:
        net = _net_rate()
    except Exception:
        net = None
    try:
        proc = psutil.Process()
        rss = proc.memory_info().rss / (1024 * 1024)
        up = max(0.0, time.time() - proc.create_time())
    except Exception:
        rss, up = 0.0, 0.0
    return {
        "cpu_pct": float(psutil.cpu_percent(interval=0.1)),
        "ram_pct": float(vm.percent),
        "disk_pct": float(disk.percent),
        "ram_used_gb": round((vm.total - vm.available) / _GB, 1),
        "ram_total_gb": round(vm.total / _GB, 1),
        "disk_used_gb": round(disk.used / _GB, 1),
        "disk_total_gb": round(disk.total / _GB, 1),
        "net_bps": net,
        "uptime_s": round(up),
        "proc_rss_mb": round(rss, 1),
    }
