"""Tiny load generator for the ChronoLens demo store.

Hammers /order continuously so SigNoz has a live p99 stream to forecast on.
    python scripts/loadgen.py [interval_ms]
"""
import sys
import time

import httpx

URL = "http://localhost:8090/order"
interval = (int(sys.argv[1]) / 1000.0) if len(sys.argv) > 1 else 0.2

sent = 0
with httpx.Client(timeout=10.0) as c:
    while True:
        try:
            c.get(URL)
            sent += 1
            if sent % 25 == 0:
                print(f"sent {sent}", flush=True)
        except Exception as exc:
            print(f"err: {exc}", flush=True)
        time.sleep(interval)
