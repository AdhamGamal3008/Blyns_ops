"""Host capacity sampling via psutil, in-process (docs/ADMIN_PORTAL.md §4.1).

sample_host() blocks ~1s for the CPU sample (spec: "CPU % (1s sample)") — the
router runs it in a worker thread so the event loop never stalls.
"""

from __future__ import annotations

import os
import time

import psutil

_PROCESS = psutil.Process()


def sample_host() -> dict:
    cpu_pct = psutil.cpu_percent(interval=1)
    load_1, load_5, load_15 = os.getloadavg()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct": cpu_pct,
        "load_avg": [load_1, load_5, load_15],
        "memory": {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "pct": vm.percent,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "pct": disk.percent,
        },
        "process": {
            "pid": _PROCESS.pid,
            "uptime_sec": int(time.time() - _PROCESS.create_time()),
            # one uvicorn worker per process; multi-worker deployments report
            # per-worker (production runs N workers behind a reverse proxy)
            "workers": 1,
        },
    }
