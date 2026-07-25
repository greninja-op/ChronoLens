"""Unit tests for CHRONO-PROOF (the SigNoz-measured counterfactual)."""
from __future__ import annotations

from chronolens.proof import build_proof


SLO = 500.0


def test_rising_then_fixed_counts_as_prevented():
    """Climbing hard pre-action, flat-and-low after → breach projected, none measured."""
    series = [200, 260, 330, 410, 480,   # pre-action climb (action at index 4)
              300, 240, 210, 205, 200]   # measured recovery after the fix
    p = build_proof(series, service="payment", slo_ms=SLO, action_index=4, step_s=15.0)
    assert p.ok
    assert p.projected_breach_s > 0          # the trend would have crossed the SLO
    assert p.measured_breach_s == 0          # reality never did
    assert p.prevented is True
    assert p.breach_seconds_avoided > 0
    assert p.peak_ms_avoided > 0


def test_not_prevented_when_measured_still_breaches():
    series = [200, 300, 400, 500, 600, 700, 720, 740]
    p = build_proof(series, service="payment", slo_ms=SLO, action_index=4, step_s=15.0)
    assert p.ok
    assert p.measured_breach_s > 0
    assert p.prevented is False


def test_flat_healthy_series_has_nothing_to_prevent():
    series = [120, 122, 119, 121, 120, 118, 121, 119]
    p = build_proof(series, service="cart", slo_ms=SLO, action_index=4, step_s=15.0)
    assert p.ok
    assert p.projected_breach_s == 0
    assert p.measured_breach_s == 0
    assert p.prevented is False
    assert p.breach_seconds_avoided == 0


def test_too_few_samples_fails_soft():
    p = build_proof([100, 200], service="x", slo_ms=SLO, action_index=1)
    assert p.ok is False
    assert p.source == "unavailable"
    assert p.notes


def test_points_cover_pre_and_post_and_are_labelled():
    series = [200, 300, 400, 480, 300, 250]
    p = build_proof(series, service="payment", slo_ms=SLO, action_index=3, step_s=10.0)
    assert len(p.points) == len(series)
    pre = [pt for pt in p.points if pt.t_offset_s <= 0]
    post = [pt for pt in p.points if pt.t_offset_s > 0]
    assert pre and post
    # post-action points carry BOTH a measured value and a projected counterfactual
    for pt in post:
        assert pt.measured_ms is not None
        assert pt.projected_ms is not None


def test_projection_follows_the_measured_pre_action_trend():
    """A steep pre-action climb must project upward, not downward."""
    series = [100, 200, 300, 400, 150, 140]
    p = build_proof(series, service="payment", slo_ms=SLO, action_index=3, step_s=15.0)
    assert p.projected_slope_ms_per_s > 0
    assert p.projected_peak_ms > series[3]


def test_narrative_and_provenance_note_present():
    series = [200, 280, 360, 450, 300, 240, 220]
    p = build_proof(series, service="payment", slo_ms=SLO, action_index=3)
    assert p.service in p.narrative
    assert p.source == "signoz"
    # provenance must be stated so projected is never mistaken for measured
    assert any("extrapolation" in n for n in p.notes)
