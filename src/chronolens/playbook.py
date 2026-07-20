"""The remediation playbook — map a *signal* to a *reversible action*.

This is what turns ChronoLens from a one-trick autoscaler into a reliability
brain: different failure signals get different fixes, and every fix is undoable.

    signal        fix (reversible lever)        why
    ------------  ----------------------------  --------------------------------
    load          scale out (+capacity)         broad latency from too much load
    dependency    circuit-break the slow dep    one downstream hop is dragging
    pool          pool-resize (+connections)    connection pool saturating
    memory        rolling restart               memory creep before OOM
    errors        rollback the deploy           error spike from a bad release

Classification uses the signal SigNoz surfaces (per-span latency, error rate,
resource pressure). In this build the demo store exposes a `dominant_signal`
field computed from its real model as a stand-in for those SigNoz metrics.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Config


@dataclass
class Play:
    signal: str
    action: str
    value: float
    why: str
    rollback: str


PLAYBOOK: dict[str, Play] = {
    "load": Play("load", "scale", 2.0,
                 "broad latency from rising load — add capacity",
                 "scale back down once load subsides"),
    "dependency": Play("dependency", "circuit-break", 0.0,
                       "a single downstream hop is slow — isolate it so it can't drag the request",
                       "close the circuit breaker when the dependency recovers"),
    "pool": Play("pool", "pool-resize", 2.0,
                 "connection pool saturating — enlarge it",
                 "resize the pool back down after the spike"),
    "memory": Play("memory", "restart", 0.0,
                   "memory creeping toward the ceiling — rolling restart before OOM",
                   "none (idempotent)"),
    "errors": Play("errors", "rollback", 0.0,
                   "error rate spiking after a change — roll back the release",
                   "re-deploy once the fix is ready"),
}

# Fallback when the signal is unknown / broadly latency-bound.
DEFAULT_PLAY = PLAYBOOK["load"]


def classify(cfg: Config, timeout: float = 6.0) -> str:
    """Ask the target what's dominating (proxy for SigNoz metrics+traces)."""
    try:
        st = httpx.get(f"{cfg.demo_store_url}/admin/status", timeout=timeout).json()
        return st.get("dominant_signal", "load")
    except Exception:
        return "load"


def play_for(signal: str) -> Play:
    return PLAYBOOK.get(signal, DEFAULT_PLAY)
