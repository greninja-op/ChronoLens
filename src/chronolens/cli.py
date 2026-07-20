"""ChronoLens command-line interface."""
from __future__ import annotations

import sys

from .config import Config
from .foresee import forecast_service, worst_service
from .loop import run_loop
from .record import Ledger
from .signoz import SigNozClient


def _print_timeline(result: dict) -> None:
    for ev in result.get("timeline", []):
        print(f"  [{ev['step']:<8}] {ev['text']}")


def cmd_services(_: list[str]) -> int:
    cfg = Config.load()
    with SigNozClient(cfg) as sn:
        services = sn.list_services(window_seconds=300)
    if not services:
        print("No services in the last 5 min. Is the demo store running + streaming to SigNoz?")
        return 1
    print(f"Found {len(services)} service(s):\n")
    for s in services:
        p99_ms = round(float(s.get("p99", 0) or 0) / 1e6, 1)
        print(f"  - {s.get('serviceName'):<20} p99={p99_ms:>8} ms  calls={s.get('numCalls', 0)}")
    return 0


def cmd_foresee(_: list[str]) -> int:
    cfg = Config.load()
    with SigNozClient(cfg) as sn:
        fc = worst_service(sn, cfg, polls=6, interval_s=2.0)
    if fc is None:
        print("No services to forecast.")
        return 1
    if fc.breaching_now:
        print(f"BREACHING NOW: {fc.service} p99={fc.current_p99_ms}ms (SLO {cfg.p99_slo_ms}ms)")
    elif fc.seconds_to_breach is not None:
        print(f"PREDICTED: {fc.service} will breach in ~{fc.seconds_to_breach:.0f}s "
              f"(p99 {fc.current_p99_ms}ms, rising {fc.slope_ms_per_s:.0f}ms/s)")
    else:
        print(f"Healthy: {fc.service} p99={fc.current_p99_ms}ms, no breach predicted.")
    return 0


def cmd_respond(args: list[str]) -> int:
    """Run one full loop. Pass 'off' to run the baseline (no action) arm."""
    managed = not (args and args[0].lower() in ("off", "baseline", "unmanaged"))
    cfg = Config.load()
    print(f"=== ChronoLens loop ({'MANAGED' if managed else 'BASELINE / OFF'}) ===\n")
    with SigNozClient(cfg) as sn:
        result = run_loop(sn, cfg, managed=managed)
    _print_timeline(result)
    if result.get("outcome"):
        print(f"\nOutcome: {result['outcome']}")
    return 0


def cmd_prevented(_: list[str]) -> int:
    ledger = Ledger()
    rows = ledger.list()
    print(f"Prevented: {ledger.prevented_count()} / {ledger.total_count()} incidents\n")
    for c in rows[-15:]:
        print(f"  {c['at']}  {c['service']:<18} {c['outcome']:<16} "
              f"p99@predict={c['p99_at_prediction_ms']}ms → final={c['final_p99_ms']}ms")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m chronolens.cli <services|foresee|respond [off]|prevented>")
        return 2
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "services":
        return cmd_services(rest)
    if cmd == "foresee":
        return cmd_foresee(rest)
    if cmd == "respond":
        return cmd_respond(rest)
    if cmd == "prevented":
        return cmd_prevented(rest)
    print(f"Unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
