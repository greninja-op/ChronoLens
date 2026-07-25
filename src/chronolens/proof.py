"""CHRONO-PROOF — prove the outage that never happened, with measured data.

The hardest thing about prevention is that success looks like *nothing happened*.
A drawn "what would have happened" curve is easy to dismiss as marketing. This
module builds the counterfactual the honest way, from SigNoz telemetry:

1. Pull the **real** p99 series for the service from SigNoz (Query Builder v5).
2. Split it at the moment ChronoLens acted.
3. Fit the trend on the **pre-action samples only** (the same EWMA/Holt machinery
   FORESEE uses) and extrapolate it across the post-action window — that's the
   *projected unmitigated path*, with a confidence band from the residual spread.
4. Overlay the **measured actual** post-action samples from SigNoz.
5. Quantify the gap: peak avoided, breach-seconds avoided, and error-budget
   (SLO-violation area) avoided.

Every number is labelled by provenance so nothing is passed off as something it
isn't:

    measured   → came from SigNoz
    projected  → linear extrapolation of the measured pre-action trend (+/- band)

That distinction is the whole point. The defused arm is real; the counterfactual
arm is an explicitly-labelled projection with an interval, not a fabricated curve.
"""
from __future__ import annotations

import calendar
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import Config
from .foresee import _ewma, _holt, _resid_std, _slope


@dataclass
class ProofPoint:
    t_offset_s: float
    measured_ms: float | None      # from SigNoz (None after the action on the A arm)
    projected_ms: float | None     # extrapolated unmitigated path (None pre-action)
    band_ms: float = 0.0           # +/- uncertainty on the projection


@dataclass
class Proof:
    service: str
    slo_ms: float
    ok: bool
    source: str                    # "signoz" | "unavailable"
    step_s: float
    action_index: int
    points: list[ProofPoint] = field(default_factory=list)

    # --- measured (from SigNoz) ---
    measured_peak_ms: float = 0.0
    measured_breach_s: float = 0.0
    measured_final_ms: float = 0.0

    # --- projected (labelled extrapolation of the pre-action trend) ---
    projected_peak_ms: float = 0.0
    projected_breach_s: float = 0.0
    projected_slope_ms_per_s: float = 0.0
    projection_band_ms: float = 0.0

    # --- the delta: what the action bought ---
    peak_ms_avoided: float = 0.0
    breach_seconds_avoided: float = 0.0
    error_budget_ms_seconds_avoided: float = 0.0
    prevented: bool = False
    confidence: float = 0.0
    narrative: str = ""
    anchor: str = ""               # how the action point was located (ledger vs peak)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["points"] = [asdict(p) for p in self.points]
        return d


def _project(pre: list[float], step_s: float, n_future: int) -> tuple[list[float], float, float]:
    """Extrapolate the pre-action trend forward. Returns (path, slope_per_s, band)."""
    if len(pre) < 2:
        last = pre[-1] if pre else 0.0
        return [last] * n_future, 0.0, 0.0

    smooth = _ewma(pre)
    _, trend_step = _holt(smooth)
    slope_step = trend_step
    ls_step = _slope(pre, 1.0)          # per-step least squares
    # same sign → average (guards a bad Holt init); else trust least squares
    slope_step = (slope_step + ls_step) / 2 if slope_step * ls_step >= 0 else ls_step

    band = round(1.5 * _resid_std(pre, smooth), 1)
    last = smooth[-1]
    path = [round(last + slope_step * (i + 1), 1) for i in range(n_future)]
    slope_per_s = round(slope_step / step_s, 2) if step_s else 0.0
    return path, slope_per_s, band


def _breach_seconds(vals: list[float], slo_ms: float, step_s: float) -> float:
    return round(sum(step_s for v in vals if v is not None and v >= slo_ms), 1)


def _area_over_slo(vals: list[float], slo_ms: float, step_s: float) -> float:
    """SLO-violation area (ms·s) — a proxy for error budget burned."""
    return round(sum(max(0.0, (v - slo_ms)) * step_s for v in vals if v is not None), 1)


def build_proof(series: list[float], *, service: str, slo_ms: float,
                action_index: int, step_s: float = 15.0,
                source: str = "signoz") -> Proof:
    """Build a Chrono-Proof from one real p99 series split at ``action_index``.

    Pure function (no I/O) so it's unit-testable without a live SigNoz.
    ``series`` is chronological p99 in ms; ``action_index`` is the sample at which
    the remediation landed.
    """
    series = [float(v) for v in (series or [])]
    if len(series) < 3 or action_index < 1 or action_index >= len(series):
        return Proof(service=service, slo_ms=slo_ms, ok=False,
                     source="unavailable", step_s=step_s, action_index=action_index,
                     notes=["not enough samples around the action to build a proof"])

    pre = series[: action_index + 1]
    post = series[action_index + 1:]
    n_future = len(post)

    projected, slope_per_s, band = _project(pre, step_s, n_future)

    points: list[ProofPoint] = []
    for i, v in enumerate(pre):
        points.append(ProofPoint(t_offset_s=round((i - action_index) * step_s, 1),
                                 measured_ms=round(v, 1), projected_ms=round(v, 1)))
    for i, (m, p) in enumerate(zip(post, projected)):
        points.append(ProofPoint(t_offset_s=round((i + 1) * step_s, 1),
                                 measured_ms=round(m, 1), projected_ms=p, band_ms=band))

    measured_peak = round(max(post) if post else pre[-1], 1)
    projected_peak = round(max(projected) if projected else pre[-1], 1)
    m_breach = _breach_seconds(post, slo_ms, step_s)
    p_breach = _breach_seconds(projected, slo_ms, step_s)
    m_area = _area_over_slo(post, slo_ms, step_s)
    p_area = _area_over_slo(projected, slo_ms, step_s)

    prevented = p_breach > 0 and m_breach == 0
    # Confidence in the counterfactual = how clean the pre-action trend was.
    spread = band / max(1.0, pre[-1])
    conf = max(0.0, min(1.0, (1.0 - spread) * (1.0 if slope_per_s > 0 else 0.4)))
    if len(pre) < 4:
        conf *= 0.6

    proof = Proof(
        service=service, slo_ms=slo_ms, ok=True, source=source, step_s=step_s,
        action_index=action_index, points=points,
        measured_peak_ms=measured_peak,
        measured_breach_s=m_breach,
        measured_final_ms=round(post[-1], 1) if post else round(pre[-1], 1),
        projected_peak_ms=projected_peak,
        projected_breach_s=p_breach,
        projected_slope_ms_per_s=slope_per_s,
        projection_band_ms=band,
        peak_ms_avoided=round(max(0.0, projected_peak - measured_peak), 1),
        breach_seconds_avoided=round(max(0.0, p_breach - m_breach), 1),
        error_budget_ms_seconds_avoided=round(max(0.0, p_area - m_area), 1),
        prevented=prevented,
        confidence=round(conf, 2),
    )
    proof.narrative = _narrate(proof)
    proof.notes.append("The 'measured' arm is SigNoz data. The 'projected' arm is a linear "
                       "extrapolation of the measured pre-action trend (+/- band) — a labelled "
                       "estimate, not a measurement.")
    return proof


def _narrate(p: Proof) -> str:
    """Plain-English proof statement — no hype, only what the numbers support."""
    if not p.ok:
        return "Not enough data to prove anything yet."
    if p.prevented:
        return (
            f"{p.service}: p99 was climbing {p.projected_slope_ms_per_s:.1f}ms/s before the fix. "
            f"Held at that trend it would have peaked near {p.projected_peak_ms:.0f}ms "
            f"(+/-{p.projection_band_ms:.0f}) and spent ~{p.projected_breach_s:.0f}s over the "
            f"{p.slo_ms:.0f}ms SLO. SigNoz measured an actual peak of {p.measured_peak_ms:.0f}ms "
            f"and {p.measured_breach_s:.0f}s over SLO — {p.breach_seconds_avoided:.0f}s of breach "
            f"avoided, {p.peak_ms_avoided:.0f}ms of peak shaved."
        )
    if p.measured_breach_s > 0:
        return (f"{p.service}: the fix did not fully hold — SigNoz measured {p.measured_breach_s:.0f}s "
                f"over the {p.slo_ms:.0f}ms SLO (peak {p.measured_peak_ms:.0f}ms).")
    return (f"{p.service}: no breach measured and none projected — nothing to prevent in this window "
            f"(peak {p.measured_peak_ms:.0f}ms vs SLO {p.slo_ms:.0f}ms).")


def _parse_iso_utc(ts: str) -> float | None:
    """Parse the ledger's ``%Y-%m-%dT%H:%M:%SZ`` stamp into a UTC epoch second."""
    if not ts:
        return None
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def action_index_from_ledger(service: str, ledger, *, step_s: float,
                             n_samples: int, now: float | None = None) -> tuple[int | None, str]:
    """Locate the sample where the remediation actually landed, from the ledger.

    The p99 series ends "now", so a case filed ``age`` seconds ago sits
    ``age / step_s`` samples back from the end. Using the *recorded* action time
    beats guessing the series peak: a still-climbing fault can peak again after
    the fix, which made the peak heuristic report "the fix didn't hold" when it
    actually had.

    Returns ``(index, provenance)``; index is None when no usable case is found.
    """
    now = now if now is not None else time.time()
    try:
        cases = [c for c in ledger.list() if c.get("service") == service]
    except Exception:
        return None, "ledger unavailable"
    # Newest case that actually took an action (skip watch-only / suggested rows).
    for case in reversed(cases):
        action = str(case.get("action") or "").strip()
        if not action or action in ("none", "pre-provision") or action.startswith("suggest:"):
            continue
        at = _parse_iso_utc(str(case.get("at") or ""))
        if at is None:
            continue
        age = now - at
        if age < 0:
            continue
        idx = int(round(n_samples - 1 - (age / step_s)))
        if 1 <= idx <= n_samples - 2:
            return idx, f"ledger case {case.get('id','?')} ({action}, {age:.0f}s ago)"
    return None, "no recent action in the ledger for this window"


def proof_from_signoz(sn, cfg: Config, service: str, *, window_seconds: int = 300,
                      step_interval: int = 15, action_index: int | None = None,
                      ledger=None) -> Proof:
    """Fetch the real p99 series from SigNoz and build the proof. Fails soft.

    The action point comes from the **ledger's recorded action time** when a
    matching case exists (precise); otherwise it falls back to the series peak
    and says so in the notes.
    """
    try:
        series = sn.service_p99_series(service, window_seconds=window_seconds,
                                      step_interval=step_interval)
    except Exception as exc:
        return Proof(service=service, slo_ms=cfg.p99_slo_ms, ok=False, source="unavailable",
                     step_s=float(step_interval), action_index=0,
                     notes=[f"SigNoz read failed: {exc}"])
    if not series:
        return Proof(service=service, slo_ms=cfg.p99_slo_ms, ok=False, source="unavailable",
                     step_s=float(step_interval), action_index=0,
                     notes=["SigNoz returned no p99 samples for this window"])

    anchor = ""
    if action_index is None:
        if ledger is None:
            from .record import Ledger
            ledger = Ledger()
        idx, why = action_index_from_ledger(service, ledger, step_s=float(step_interval),
                                           n_samples=len(series))
        if idx is not None:
            action_index, anchor = idx, "action time from " + why
        else:
            # Fallback: the series peak, where remediation most likely kicked in.
            action_index = max(1, series.index(max(series)))
            if len(series) >= 3:
                action_index = min(action_index, len(series) - 2)
            anchor = f"action point estimated from the series peak ({why})"

    proof = build_proof(series, service=service, slo_ms=cfg.p99_slo_ms,
                        action_index=action_index, step_s=float(step_interval),
                        source="signoz")
    if anchor:
        proof.anchor = anchor
        proof.notes.append(anchor)
    return proof
