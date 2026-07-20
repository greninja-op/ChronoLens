"""FORESEE — turn a climbing latency trend into a time-to-breach forecast.

Deliberately boring math: sample the service p99 a few times, fit the rate of
change, and project it forward to the SLO. Boring wins here because it's
explainable ("p99 rising ~40ms/s, breach in ~25s") and needs no training data.
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


def forecast_service(
    sn: SigNozClient,
    service: str,
    slo_ms: float,
    *,
    polls: int = 6,
    interval_s: float = 2.0,
    lead_window_s: float = 120.0,
) -> Forecast:
    """Poll a service's p99 and project when it will cross ``slo_ms``."""
    samples: list[float] = []
    for i in range(max(2, polls)):
        samples.append(sn.service_p99_ms(service))
        if i < polls - 1:
            time.sleep(interval_s)

    current = samples[-1]
    slope = _slope(samples, interval_s)

    if current >= slo_ms:
        return Forecast(service, current, slope, 0.0, True, samples)

    seconds = None
    if slope > 0.5:  # meaningfully rising
        eta = (slo_ms - current) / slope
        if 0 < eta <= lead_window_s:
            seconds = round(eta, 1)
    return Forecast(service, current, slope, seconds, False, samples)


def worst_service(sn: SigNozClient, cfg: Config, **kwargs) -> Forecast | None:
    """Forecast every live service; return the one closest to breaching."""
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
