"""Verify answer-quality grading reads response text from SigNoz logs.

    python scripts/verify_quality_logs.py
"""
from __future__ import annotations

import time

import httpx

AGENT = "http://localhost:8091"
APP = "http://localhost:8095"


def main() -> int:
    with httpx.Client(timeout=30) as c:
        c.get(f"{AGENT}/admin/mode", params={"mode": "normal"})
        for _ in range(8):
            c.get(f"{AGENT}/chat")
    print("drove 8 agent turns; waiting for the logs pipeline…")
    time.sleep(25)

    from chronolens.config import Config
    from chronolens.signoz import SigNozClient
    cfg = Config.load()
    with SigNozClient(cfg) as sn:
        bodies = sn.agent_response_bodies("chronolens-agent", limit=8)
    print(f"response bodies read from SigNoz logs: {len(bodies)}")
    for b in bodies[:3]:
        print(f"   · {b[:90]}")

    r = httpx.get(f"{APP}/api/agent/quality?samples=8", timeout=120).json()
    print(f"\n/api/agent/quality -> data_source={r.get('data_source')} "
          f"graded={r.get('graded')} avg={r.get('avg_score')} verdict={r.get('verdict')}")
    ok = r.get("data_source") == "signoz"
    print("RESULT:", "OK — graded from SigNoz logs" if ok
          else "FELL BACK to driving the agent (no log bodies in SigNoz)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
