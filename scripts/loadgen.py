"""Tiny load generator for the demo store — drives /order continuously.

Used to give SigNoz a real p99 series to forecast against.

    python scripts/loadgen.py [seconds] [rps]
"""
from __future__ import annotations

import sys
import time

import httpx

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
RPS = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
URL = "http://localhost:8090/order"

deadline = time.time() + DURATION
gap = 1.0 / max(0.5, RPS)
sent = 0
with httpx.Client(timeout=10.0) as c:
    while time.time() < deadline:
        try:
            c.get(URL)
            sent += 1
        except Exception:
            pass
        time.sleep(gap)
print(f"loadgen done: {sent} requests over {DURATION:.0f}s")
