"""FORESEE — turn a climbing latency trend into a time-to-breach forecast.

Deliberately boring math: sample the service p99 a few times, fit the rate of
change, and project it forward to the SLO. Boring wins here because it's
explainable ("p99 rising ~40ms/s, breach in ~25s") and needs no training data.

A **confidence guard** sits in front of the projection so ChronoLens doesn't act
on noise: it needs enough samples, a slope above a noise floor, and a *sustained*
rise (most consecutive steps trending up) before it will call a breach.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import Config
from .signoz import SigNozClient


@dataclass
class Forecast:
    service: str
    current_p99_ms: float
    slope_ms_per_s: float
    seconds_to_breach: float | None  # None = not trending toward a breach
    breaching_now: bool
    samples: list[float] = field(default_factory=list)
    confidence: float = 1.0          # 0..1 — how trustworthy this trend is
    confident: bool = True           # passed the confidence guard?
    reason: str = ""                 # why we did/didn't trust it

    @property
    def predicted(self) -> bool:
        return self.breaching_now or self.seconds_to_breach is not None


def _slope(samples: list[float], interval_s: float) -> float:
    """Least-squares slope (ms per second) over evenly spaced samples."""
    n = len(samples)
    if n < 2:
        return 0.0
    xs = [i * interval_s for i in range(n)]
    mx = sum(xs) / n
    my = sum(samples) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, samples))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def _sustained_fraction(samples: list[float]) -> float:
    """Fraction of consecutive steps that rise — 1.0 = monotonic climb."""
    if len(samples) < 2:
        return 0.0
    ups = sum(1 for a, b in zip(samples, samples[1:]) if b >= a)
    return ups / (len(samples) - 1)


def confidence_guard(
    samples: list[float],
    slope: float,
    *,
    min_samples: int = 4,
    min_slope_ms_per_s: float = 3.0,
) -> tuple[bool, float, str]:
    """Decide whether a rising trend is trustworthy enough to act on.

    Returns ``(confident, confidence_0_1, reason)``. Guards against three ways a
    forecast lies: too few samples, a slope inside the noise floor, and a jagged
    (non-sustained) series that merely looks like it's climbing.
    """
    n = len(samples)
    if n < min_samples:
        return False, 0.2, f"only {n} samples (<{min_samples}) — not enough to trust."
    if slope < min_slope_ms_per_s:
        return False, 0.3, f"slope {slope:.1f}ms/s below noise floor {min_slope_ms_per_s}ms/s."
    sustained = _sustained_fraction(samples)
    if sustained < 0.6:
        return False, round(sustained, 2), f"trend not sustained ({sustained:.0%} of steps rising)."
    # confidence blends how sustained it is with how far above the noise floor.
    conf = min(1.0, 0.5 * sustained + 0.5 * min(1.0, slope / (min_slope_ms_per_s * 4)))
    return True, round(conf, 2), f"sustained rise ({sustained:.0%} of steps), slope {slope:.1f}ms/s."


def forecast_service(
    sn: SigNozClient,
    service: str,
    slo_ms: float,
    *,
    polls: int = 6,
    interval_s: float = 2.0,
    lead_window_s: float = 120.0,
    min_samples: int = 4,
    min_slope_ms_per_s: float = 3.0,
) -> Forecast:
    """Poll a service's p99 and project when it will cross ``slo_ms``."""
    samples: list[float] = []
    for i in range(max(2, polls)):
        samples.append(sn.service_p99_ms(service))
        if i < polls - 1:
            time.sleep(interval_s)

    current = samples[-1]
    slope = _slope(samples, interval_s)
    confident, conf, reason = confidence_guard(
        samples, slope, min_samples=min_samples, min_slope_ms_per_s=min_slope_ms_per_s
    )

    if current >= slo_ms:
        # Already breaching — that's a measurement, not a prediction; always act.
        return Forecast(service, current, slope, 0.0, True, samples,
                        confidence=1.0, confident=True, reason="already at/over SLO.")

    seconds = None
    if confident and slope > 0:
        eta = (slo_ms - current) / slope
        if 0 < eta <= lead_window_s:
            seconds = round(eta, 1)
    return Forecast(service, current, slope, seconds, False, samples,
                    confidence=conf, confident=confident, reason=reason)


def worst_service(sn: SigNozClient, cfg: Config, **kwargs) -> Forecast | None:
    """Forecast every live service; return the one closest to breaching."""
    kwargs.setdefault("min_samples", cfg.min_samples)
    kwargs.setdefault("min_slope_ms_per_s", cfg.min_slope_ms_per_s)
    services = [s.get("serviceName") for s in sn.list_services(window_seconds=300)]
    services = [s for s in services if s and s != "chronolens"]  # skip our own trace
    forecasts = [forecast_service(sn, s, cfg.p99_slo_ms, **kwargs) for s in services]
    predicted = [f for f in forecasts if f.predicted]
    if predicted:
        # breaching first, then soonest to breach
        predicted.sort(key=lambda f: (not f.breaching_now, f.seconds_to_breach or 1e9))
        return predicted[0]
    if forecasts:
        forecasts.sort(key=lambda f: f.current_p99_ms, reverse=True)
        return forecasts[0]
    return None
