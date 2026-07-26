"""Demo readiness check — exercises every path a judge would touch.

    python scripts/demo_check.py

Prints a PASS/FAIL line per capability so nothing is assumed to work.
"""
from __future__ import annotations

import os
import sys

import httpx

APP = "http://localhost:8095"
STORE = "http://localhost:8090"
AGENT = "http://localhost:8091"
SIGNOZ = "http://localhost:8080"
MCP = "http://localhost:8000/livez"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

results: list[tuple[bool, str, str]] = []


def check(name: str, fn) -> None:
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {str(exc)[:90]}"
    results.append((ok, name, detail))


def _up(url: str):
    def go():
        r = httpx.get(url, timeout=15)
        return r.status_code < 500, f"HTTP {r.status_code}"
    return go


def _json(path: str, pred, timeout: float = 90.0):
    def go():
        r = httpx.get(APP + path, timeout=timeout)
        d = r.json()
        ok, detail = pred(d)
        return ok, detail
    return go


def main() -> int:
    # ── infrastructure ────────────────────────────────────────────────────
    check("SigNoz UI reachable", _up(SIGNOZ))
    check("SigNoz MCP live", _up(MCP))
    check("Demo store running", _up(STORE + "/admin/status"))
    check("Demo agent running", _up(AGENT + "/health"))
    check("Mission Control serving", _up(APP + "/"))

    # ── repo artefacts the rules require ──────────────────────────────────
    for f in ("casting.yaml", "casting.yaml.lock", "README.md",
              "CHRONOLENS_BLOG.md", "SUBMISSION.md", "ERROR-AND-FIXES.md"):
        check(f"file: {f}",
              lambda f=f: (os.path.isfile(os.path.join(ROOT, f)), "present"))

    # ── SigNoz reads ──────────────────────────────────────────────────────
    check("SigNoz sees services", _json(
        "/api/services",
        lambda d: (bool(d.get("services")), f"{len(d.get('services') or [])} service(s)")))
    check("SigNoz integration status", _json(
        "/api/signoz",
        lambda d: (bool(d.get("connected")),
                   f"guard={d.get('guard_alerts')} firing={d.get('firing')} "
                   f"channels={len(d.get('channels') or [])}")))

    # ── the three headline features ───────────────────────────────────────
    check("Chrono-Proof (measured counterfactual)", _json(
        "/api/proof",
        lambda d: (bool(d.get("ok")),
                   f"source={d.get('source')} avoided={d.get('breach_seconds_avoided')}s "
                   f"prevented={d.get('prevented')}")))
    check("Blast radius (dependency graph)", _json(
        "/api/blast",
        lambda d: (bool(d.get("ok")),
                   f"topology={d.get('topology_source')} root={d.get('root_service')} "
                   f"victims={len(d.get('victims') or [])}")))
    check("MCP server + tools", _json(
        "/api/mcp/status",
        lambda d: (bool(d.get("connected")),
                   f"{d.get('server')} · {d.get('tool_count')} tools")))

    # ── MCP co-pilot (a real tools/call) ──────────────────────────────────
    def copilot():
        r = httpx.post(APP + "/api/mcp/chat",
                       json={"query": "which services are slowest right now?"}, timeout=120)
        d = r.json()
        calls = d.get("tool_calls") or []
        ok = bool(d.get("mcp_connected")) and bool(calls) and all(c["ok"] for c in calls)
        return ok, f"{len(calls)} tool call(s): " + ", ".join(c["tool"] for c in calls)
    check("MCP co-pilot answers via tools/call", copilot)

    # ── Agent Watch, all three, telemetry-driven ──────────────────────────
    check("Agent Watch · drift (from SigNoz)", _json(
        "/api/agent/drift?samples=8",
        lambda d: (d.get("data_source") == "signoz",
                   f"data_source={d.get('data_source')} score={(d.get('drift') or {}).get('score')}")))
    check("Agent Watch · loop breaker (from SigNoz)", _json(
        "/api/agent/loopcheck",
        lambda d: (d.get("data_source") == "signoz",
                   f"data_source={d.get('data_source')} "
                   f"looping={(d.get('verdict') or {}).get('looping')}")))
    check("Agent Watch · quality (from SigNoz logs)", _json(
        "/api/agent/quality?samples=6",
        lambda d: (d.get("data_source") == "signoz",
                   f"data_source={d.get('data_source')} graded={d.get('graded')} "
                   f"avg={d.get('avg_score')}")))

    # ── the ledger / receipts ─────────────────────────────────────────────
    check("Prevention ledger has receipts", _json(
        "/api/prevented",
        lambda d: (int(d.get("total") or 0) > 0,
                   f"{d.get('prevented')}/{d.get('total')} prevented, ${d.get('dollars_saved')}")))

    # ── channels ──────────────────────────────────────────────────────────
    check("Slack approve-to-act configured", _json(
        "/api/config", lambda d: (bool(d.get("slack")), f"slack={d.get('slack')}")))
    check("WhatsApp configured (optional)", _json(
        "/api/config", lambda d: (bool(d.get("whatsapp")), f"whatsapp={d.get('whatsapp')}")))

    # ── report ────────────────────────────────────────────────────────────
    width = max(len(n) for _, n, _ in results)
    print("\n=== ChronoLens demo readiness ===\n")
    for ok, name, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}]  {name.ljust(width)}  {detail}")
    failed = [n for ok, n, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("Needs attention: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
