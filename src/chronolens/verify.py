"""VERIFY — watch SigNoz to confirm the breach was actually avoided.

The loop grades its own homework. After a reversible action, poll the service's
p99 through the grace window. If it settles back under the SLO, it's a save. If
not, the caller rolls the action back and escalates.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .signoz import SigNozClient


@dataclass
class Verification:
    verified: bool
    final_p99_ms: float
    peak_p99_ms: float
    samples: list[float] = field(default_factory=list)


def verify(
    sn: SigNozClient,
    service: str,
    slo_ms: float,
    *,
    checks: int = 14,
    interval_s: float = 3.0,
) -> Verification:
    """Confirm the service stays under the SLO after remediation.

    Note on windowed metrics: SigNoz p99 is computed over a rolling window, so
    after a fix the tail only drops once the backlog of slow traces ages out of
    that window. We therefore poll patiently (a few window-widths) rather than
    grading the fix in the first couple of seconds.
    """
    samples: list[float] = []
    for i in range(max(2, checks)):
        samples.append(sn.service_p99_ms(service))
        if i < checks - 1:
            time.sleep(interval_s)
    final = samples[-1]
    peak = max(samples)
    # "verified" = it ended healthy and the tail is trending down, not up.
    trending_down = samples[-1] <= samples[0]
    return Verification(
        verified=final < slo_ms and trending_down,
        final_p99_ms=final,
        peak_p99_ms=peak,
        samples=samples,
    )
