"""FORESEE — turn a climbing latency trend into a time-to-breach forecast.

The math stays explainable on purpose ("p99 rising ~40ms/s, breach in ~25s"),
but it's sturdier than a bare slope now:

* **EWMA smoothing** damps single-sample jitter before we read the trend.
* **Holt's linear trend** (double-exponential smoothing) estimates the rate of
  change, so a noisy series doesn't swing the forecast around.
* a **confidence interval** (from the residual spread) gives an ETA *range*, not
  a false-precision point.
* a **confidence guard** still gates action: enough samples, slope above a noise
  floor, and a sustained rise.
* **multi-signal** — an elevated error rate corroborates a latency trend and
  lifts confidence (a second, independent signal that something's wrong).
"""
from __future__ import annotations

import math
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
    band_ms: float = 0.0             # +/- confidence band on the latest value
    eta_low_s: float | None = None   # optimistic edge of the breach ETA
    eta_high_s: float | None = None  # pessimistic edge of the breach ETA
    error_rate: float = 0.0          # corroborating signal (fraction 0..1)

    @property
    def predicted(self) -> bool:
        return self.breaching_now or self.seconds_to_breach is not None


# --------------------------------------------------------------------------- #
# smoothing / trend primitives
# --------------------------------------------------------------------------- #
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


def _ewma(xs: list[float], alpha: float = 0.4) -> list[float]:
    if not xs:
        return []
    out = [xs[0]]
    for x in xs[1:]:
        out.append(alpha * x + (1 - alpha) * out[-1])
    return out


def _holt(xs: list[float], alpha: float = 0.5, beta: float = 0.3) -> tuple[float, float]:
    """Holt's linear trend. Returns (level, trend-per-step)."""
    n = len(xs)
    if n < 2:
        return (xs[-1] if xs else 0.0), 0.0
    level = xs[0]
    trend = xs[1] - xs[0]
    for x in xs[1:]:
        last = level
        level = alpha * x + (1 - alpha) * (level + trend)
        trend = beta * (level - last) + (1 - beta) * trend
    return level, trend


def _resid_std(raw: list[float], smooth: list[float]) -> float:
    diffs = [r - s for r, s in zip(raw, smooth)]
    if len(diffs) < 2:
        return 0.0
    m = sum(diffs) / len(diffs)
    var = sum((d - m) ** 2 for d in diffs) / len(diffs)
    return math.sqrt(var)


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
    """Decide whether a rising trend is trustworthy enough to act on."""
    n = len(samples)
    if n < min_samples:
        return False, 0.2, f"only {n} samples (<{min_samples}) — not enough to trust."
    if slope < min_slope_ms_per_s:
        return False, 0.3, f"slope {slope:.1f}ms/s below noise floor {min_slope_ms_per_s}ms/s."
    sustained = _sustained_fraction(samples)
    if sustained < 0.6:
        return False, round(sustained, 2), f"trend not sustained ({sustained:.0%} of steps rising)."
    conf = min(1.0, 0.5 * sustained + 0.5 * min(1.0, slope / (min_slope_ms_per_s * 4)))
    return True, round(conf, 2), f"sustained rise ({sustained:.0%} of steps), slope {slope:.1f}ms/s."


# --------------------------------------------------------------------------- #
# the analyzer (shared by the loop poll and the fast /api/forecast)
# --------------------------------------------------------------------------- #
def analyze(
    samples: list[float],
    interval_s: float,
    slo_ms: float,
    *,
    min_samples: int = 4,
    min_slope_ms_per_s: float = 3.0,
    lead_window_s: float = 120.0,
    error_rate: float = 0.0,
) -> Forecast:
    """Turn a raw p99 series into a Forecast with smoothing + a confidence band."""
    samples = [float(s) for s in samples]
    service = ""  # filled by callers
    if not samples:
        return Forecast(service, 0.0, 0.0, None, False, [], 0.0, False, "no data")

    smooth = _ewma(samples)
    _, trend_step = _holt(smooth)
    slope = trend_step / interval_s if interval_s else 0.0
    # sanity-blend with least squares so a bad Holt init can't dominate
    ls = _slope(samples, interval_s)
    if slope * ls >= 0:  # same sign → average them; else trust least squares
        slope = (slope + ls) / 2
    else:
        slope = ls

    current = samples[-1]
    band = round(1.5 * _resid_std(samples, smooth), 1)
    confident, conf, reason = confidence_guard(
        smooth, slope, min_samples=min_samples, min_slope_ms_per_s=min_slope_ms_per_s
    )

    # an elevated error rate is a second, independent signal — it lifts confidence.
    if error_rate >= 0.02:
        conf = min(1.0, conf + 0.15)
        reason += f" (+ {error_rate*100:.0f}% errors corroborate)"

    if current >= slo_ms:
        return Forecast(service, current, slope, 0.0, True, samples,
                        confidence=1.0, confident=True, reason="already at/over SLO.",
                        band_ms=band, error_rate=error_rate)

    seconds = eta_low = eta_high = None
    if confident and slope > 0:
        eta = (slo_ms - current) / slope
        if 0 < eta <= lead_window_s:
            seconds = round(eta, 1)
            eta_low = round(max(0.0, (slo_ms - (current + band)) / slope), 1)
            eta_high = round((slo_ms - max(0.0, current - band)) / slope, 1)
    return Forecast(service, current, slope, seconds, False, samples,
                    confidence=conf, confident=confident, reason=reason,
                    band_ms=band, eta_low_s=eta_low, eta_high_s=eta_high,
                    error_rate=error_rate)


def forecast_from_series(
    service: str, samples: list[float], slo_ms: float, *, interval_s: float = 15.0,
    error_rate: float = 0.0, **kw,
) -> Forecast:
    """Fast path: analyze an already-fetched series (one SigNoz query, no sleeps)."""
    fc = analyze(samples, interval_s, slo_ms, error_rate=error_rate, **kw)
    fc.service = service
    return fc


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
    """Poll a service's p99 live and project when it will cross ``slo_ms``."""
    samples: list[float] = []
    for i in range(max(2, polls)):
        samples.append(sn.service_p99_ms(service))
        if i < polls - 1:
            time.sleep(interval_s)
    err = 0.0
    try:
        err = sn.service_error_rate(service)
    except Exception:
        pass
    fc = analyze(samples, interval_s, slo_ms, min_samples=min_samples,
                 min_slope_ms_per_s=min_slope_ms_per_s, lead_window_s=lead_window_s,
                 error_rate=err)
    fc.service = service
    return fc


def worst_service(sn: SigNozClient, cfg: Config, **kwargs) -> Forecast | None:
    """Forecast every live service; return the one closest to breaching."""
    kwargs.setdefault("min_samples", cfg.min_samples)
    kwargs.setdefault("min_slope_ms_per_s", cfg.min_slope_ms_per_s)
    services = [s.get("serviceName") for s in sn.list_services(window_seconds=300)]
    services = [s for s in services if s and s != "chronolens"]  # skip our own trace
    forecasts = [forecast_service(sn, s, cfg.p99_slo_ms, **kwargs) for s in services]
    predicted = [f for f in forecasts if f.predicted]
    if predicted:
        predicted.sort(key=lambda f: (not f.breaching_now, f.seconds_to_breach or 1e9))
        return predicted[0]
    if forecasts:
        forecasts.sort(key=lambda f: f.current_p99_ms, reverse=True)
        return forecasts[0]
    return None
