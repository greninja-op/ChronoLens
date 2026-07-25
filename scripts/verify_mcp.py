"""Live verification of the MCP integration through the HTTP API.

    python scripts/verify_mcp.py
"""
from __future__ import annotations

import httpx

BASE = "http://localhost:8095"
QUESTIONS = [
    "which services are slowest right now?",
    "are any alerts firing?",
    "any error logs in the last hour?",
    "top operations for chronolens-store",
]


def main() -> int:
    s = httpx.get(f"{BASE}/api/mcp/status", timeout=60).json()
    print(f"MCP status : connected={s.get('connected')} "
          f"server={s.get('server')} tools={s.get('tool_count')}")
    if not s.get("connected"):
        print("  error:", s.get("error"))
        return 1

    failures = 0
    for q in QUESTIONS:
        r = httpx.post(f"{BASE}/api/mcp/chat", json={"query": q}, timeout=120).json()
        calls = ", ".join(f"{t['tool']}({t['rows']} rows)" for t in r.get("tool_calls", []))
        ok = bool(r.get("mcp_connected")) and all(t["ok"] for t in r.get("tool_calls", []))
        failures += 0 if ok else 1
        print(f"\nQ: {q}")
        print(f"   intent : {r.get('intent')}")
        print(f"   tools  : {calls or 'none'}")
        print(f"   answer : {r.get('answer', '')[:160]}")
        print(f"   status : {'OK' if ok else 'FAILED'}")
    print(f"\n{len(QUESTIONS) - failures}/{len(QUESTIONS)} questions answered via MCP")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
