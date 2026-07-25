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


# --------------------------------------------------------------------------- #
# Anchoring the action point to the ledger's recorded action time.             #
# --------------------------------------------------------------------------- #
import calendar
import time

from chronolens.proof import action_index_from_ledger


class _FakeLedger:
    def __init__(self, cases): self._cases = cases
    def list(self): return self._cases


def _stamp(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def test_action_index_derived_from_recorded_action_time():
    """A case filed 60s ago, 15s steps, 12 samples -> 4 samples back from the end."""
    now = calendar.timegm((2026, 7, 26, 12, 0, 0, 0, 0, 0))
    led = _FakeLedger([{ "id":"abc", "service":"payment", "action":"scale", "at":_stamp(now-60) }])
    idx, why = action_index_from_ledger("payment", led, step_s=15.0, n_samples=12, now=now)
    assert idx == 12 - 1 - 4
    assert "ledger case abc" in why


def test_non_action_cases_are_ignored():
    """watch-only / suggested / pre-provision rows never anchor a proof."""
    now = calendar.timegm((2026, 7, 26, 12, 0, 0, 0, 0, 0))
    led = _FakeLedger([
        {"id":"a","service":"payment","action":"none","at":_stamp(now-60)},
        {"id":"b","service":"payment","action":"pre-provision","at":_stamp(now-55)},
        {"id":"c","service":"payment","action":"suggest:scale","at":_stamp(now-50)},
    ])
    idx, why = action_index_from_ledger("payment", led, step_s=15.0, n_samples=12, now=now)
    assert idx is None
    assert "no recent action" in why


def test_other_services_are_ignored():
    now = calendar.timegm((2026, 7, 26, 12, 0, 0, 0, 0, 0))
    led = _FakeLedger([{ "id":"x", "service":"orders", "action":"scale", "at":_stamp(now-60) }])
    idx, _ = action_index_from_ledger("payment", led, step_s=15.0, n_samples=12, now=now)
    assert idx is None


def test_action_outside_the_window_is_rejected():
    """An action 2 hours old can't be anchored inside a 3-minute series."""
    now = calendar.timegm((2026, 7, 26, 12, 0, 0, 0, 0, 0))
    led = _FakeLedger([{ "id":"old", "service":"payment", "action":"scale", "at":_stamp(now-7200) }])
    idx, _ = action_index_from_ledger("payment", led, step_s=15.0, n_samples=12, now=now)
    assert idx is None


def test_newest_action_case_wins():
    now = calendar.timegm((2026, 7, 26, 12, 0, 0, 0, 0, 0))
    led = _FakeLedger([
        {"id":"older","service":"payment","action":"scale","at":_stamp(now-120)},
        {"id":"newer","service":"payment","action":"pool-resize","at":_stamp(now-45)},
    ])
    idx, why = action_index_from_ledger("payment", led, step_s=15.0, n_samples=12, now=now)
    assert "newer" in why
    assert idx == 12 - 1 - 3


def test_ledger_failure_fails_soft():
    class _Broken:
        def list(self): raise RuntimeError("ledger gone")
    idx, why = action_index_from_ledger("payment", _Broken(), step_s=15.0, n_samples=10)
    assert idx is None
    assert "unavailable" in why
