"""Property-based + unit tests for the ChronoLens closed loop.

Covers the pure logic behind each stage so the loop's decisions are provably
correct without a live SigNoz: slope fitting, the confidence guard, breach
projection, the ledger, the cost model, seasonality, the playbook, anti-flap
guardrails, and the trust ladder.
"""
from __future__ import annotations

import pytest

try:  # hypothesis ships a native extension that some locked-down hosts block
    from hypothesis import given, settings
    from hypothesis import strategies as st
except Exception:  # pragma: no cover - environment-dependent
    pytest.skip("hypothesis unavailable in this environment", allow_module_level=True)

from chronolens.dollars import units_to_dollars
from chronolens.foresee import (
    Forecast,
    _slope,
    _sustained_fraction,
    confidence_guard,
    forecast_service,
)
from chronolens.governance import decide, proven_saves_for
from chronolens.guardrails import FlapGuard
from chronolens.learn import detect_seasonality, recall
from chronolens.playbook import DEFAULT_PLAY, PLAYBOOK, play_for
from chronolens.record import CaseFile, Ledger, new_case


# --------------------------------------------------------------------------- #
# config stub
# --------------------------------------------------------------------------- #
class Cfg:
    def __init__(self, **kw):
        self.p99_slo_ms = kw.get("p99_slo_ms", 500.0)
        self.autonomy = kw.get("autonomy", "auto")
        self.trust_min_saves = kw.get("trust_min_saves", 3)
        self.min_dwell_s = kw.get("min_dwell_s", 20.0)
        self.max_capacity = kw.get("max_capacity", 12.0)
        self.min_slope_ms_per_s = kw.get("min_slope_ms_per_s", 3.0)
        self.min_samples = kw.get("min_samples", 4)
        self.cost_per_unit_hr = kw.get("cost_per_unit_hr", 0.65)


# --------------------------------------------------------------------------- #
# FORESEE — slope, confidence guard, breach projection
# --------------------------------------------------------------------------- #
@given(
    intercept=st.floats(min_value=0, max_value=500, allow_nan=False),
    rate=st.floats(min_value=-50, max_value=50, allow_nan=False),
    n=st.integers(min_value=2, max_value=12),
)
def test_slope_recovers_linear_rate(intercept, rate, n):
    interval = 2.0
    samples = [intercept + rate * (i * interval) for i in range(n)]
    got = _slope(samples, interval)
    assert abs(got - rate) < 1e-6


def test_slope_of_flat_series_is_zero():
    assert _slope([100.0] * 6, 2.0) == 0.0


def test_sustained_fraction_monotonic_is_one():
    assert _sustained_fraction([1, 2, 3, 4, 5]) == 1.0
    assert _sustained_fraction([5, 4, 3, 2, 1]) == 0.0


@given(n=st.integers(min_value=0, max_value=3))
def test_confidence_guard_rejects_too_few_samples(n):
    ok, conf, _ = confidence_guard([100.0] * n, 10.0, min_samples=4)
    assert not ok


def test_confidence_guard_rejects_noise_floor():
    ok, _, _ = confidence_guard([100, 101, 100, 101, 100], 1.0,
                                min_samples=4, min_slope_ms_per_s=3.0)
    assert not ok


def test_confidence_guard_accepts_sustained_climb():
    ok, conf, _ = confidence_guard([100, 140, 180, 220, 260], 20.0,
                                   min_samples=4, min_slope_ms_per_s=3.0)
    assert ok and 0 < conf <= 1.0


class ScriptedSN:
    """Fake SigNoz that returns a fixed p99 sequence, one per poll."""

    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def service_p99_ms(self, service, window_seconds=120):
        v = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return v


def test_forecast_projects_breach_from_rising_trend():
    # rising ~50ms/s from 250ms toward a 500ms SLO -> breach in ~5s
    sn = ScriptedSN([250, 300, 350, 400, 450])
    fc = forecast_service(sn, "svc", 500.0, polls=5, interval_s=1.0,
                          min_samples=4, min_slope_ms_per_s=3.0)
    assert fc.predicted and fc.seconds_to_breach is not None
    assert 0 < fc.seconds_to_breach <= 10


def test_forecast_ignores_flat_healthy_series():
    sn = ScriptedSN([120, 121, 119, 120, 121])
    fc = forecast_service(sn, "svc", 500.0, polls=5, interval_s=1.0)
    assert not fc.predicted and not fc.confident


def test_forecast_flags_already_breaching():
    sn = ScriptedSN([600, 610, 620])
    fc = forecast_service(sn, "svc", 500.0, polls=3, interval_s=1.0)
    assert fc.breaching_now and fc.seconds_to_breach == 0.0


# --------------------------------------------------------------------------- #
# RECORD — ledger round-trips and aggregates
# --------------------------------------------------------------------------- #
def _case(**kw) -> CaseFile:
    base = dict(service="svc", predicted_breach_in_s=5.0, p99_at_prediction_ms=420.0,
                slo_ms=500.0, action="scale", rollback="down", verified=True,
                final_p99_ms=380.0, peak_p99_ms=430.0, outcome="breach avoided")
    base.update(kw)
    return new_case(**base)


def test_ledger_counts_only_avoided_and_sums_dollars(tmp_path):
    led = Ledger(root=str(tmp_path))
    led.record(_case(outcome="breach avoided", cost_units_returned=2, dollars_saved=1.30))
    led.record(_case(outcome="escalated"))
    led.record(_case(outcome="breach avoided", cost_units_returned=2, dollars_saved=1.30))
    assert led.prevented_count() == 2
    assert led.total_count() == 3
    assert led.total_dollars_saved() == 2.60


# --------------------------------------------------------------------------- #
# COST — units to dollars
# --------------------------------------------------------------------------- #
@given(units=st.floats(min_value=0, max_value=1e4, allow_nan=False),
       rate=st.floats(min_value=0, max_value=100, allow_nan=False))
def test_dollars_non_negative_and_scales(units, rate):
    d = units_to_dollars(units, Cfg(cost_per_unit_hr=rate))
    assert d >= 0
    assert abs(d - round(units * rate, 2)) < 0.01


def test_dollars_clamps_negative_units():
    assert units_to_dollars(-5, Cfg(cost_per_unit_hr=1.0)) == 0.0


# --------------------------------------------------------------------------- #
# LEARN — seasonality
# --------------------------------------------------------------------------- #
def test_detect_seasonality_finds_recurring_hour():
    rows = [{"load_onset_at": "2026-07-2{}T17:04:00Z".format(d)} for d in range(3)]
    hour, due, note = detect_seasonality(rows, now_hour=17)
    assert hour == 17 and due is True and "17:00" in note


def test_detect_seasonality_needs_repeats():
    rows = [{"load_onset_at": "2026-07-20T09:00:00Z"}]
    hour, due, _ = detect_seasonality(rows, now_hour=9, min_repeats=2)
    assert hour is None and due is False


def test_recall_raises_floor_for_repeat_offender(tmp_path):
    led = Ledger(root=str(tmp_path))
    led.record(_case(service="checkout"))
    mem = recall("checkout", led)
    assert mem.is_repeat_offender and mem.recommended_floor >= 2.0


# --------------------------------------------------------------------------- #
# PLAYBOOK — every signal maps to a reversible action
# --------------------------------------------------------------------------- #
@given(signal=st.sampled_from(list(PLAYBOOK.keys())))
def test_play_for_known_signals(signal):
    play = play_for(signal)
    assert play.action in {"scale", "circuit-break", "pool-resize", "restart", "rollback"}
    assert play.rollback  # every action documents how to undo it


def test_play_for_unknown_defaults_to_scale():
    assert play_for("something-new") is DEFAULT_PLAY
    assert DEFAULT_PLAY.action == "scale"


# --------------------------------------------------------------------------- #
# GUARDRAILS — anti-flap
# --------------------------------------------------------------------------- #
def test_guard_blocks_within_dwell(tmp_path):
    g = FlapGuard(root=str(tmp_path))
    g.note_action("svc", "scale")
    v = g.check("svc", "scale", min_dwell_s=60, current_capacity=2,
                scale_value=2, max_capacity=12)
    assert not v.allowed and "anti-flap" in v.reason


def test_guard_allows_after_dwell(tmp_path):
    g = FlapGuard(root=str(tmp_path))
    v = g.check("fresh", "scale", min_dwell_s=0, current_capacity=2,
                scale_value=2, max_capacity=12)
    assert v.allowed


def test_guard_clamps_at_ceiling(tmp_path):
    g = FlapGuard(root=str(tmp_path))
    v = g.check("svc", "scale", min_dwell_s=0, current_capacity=11,
                scale_value=4, max_capacity=12)
    assert v.allowed and v.capped_value == 1.0


def test_guard_blocks_at_ceiling(tmp_path):
    g = FlapGuard(root=str(tmp_path))
    v = g.check("svc", "scale", min_dwell_s=0, current_capacity=12,
                scale_value=2, max_capacity=12)
    assert not v.allowed


# --------------------------------------------------------------------------- #
# GOVERNANCE — the trust ladder
# --------------------------------------------------------------------------- #
def test_auto_always_acts(tmp_path):
    led = Ledger(root=str(tmp_path))
    assert decide(Cfg(autonomy="auto"), "svc", led).may_act


def test_suggest_never_acts(tmp_path):
    led = Ledger(root=str(tmp_path))
    assert not decide(Cfg(autonomy="suggest"), "svc", led).may_act


def test_earn_acts_only_after_proven_saves(tmp_path):
    led = Ledger(root=str(tmp_path))
    cfg = Cfg(autonomy="earn", trust_min_saves=2)
    assert not decide(cfg, "svc", led).may_act  # 0 saves
    led.record(_case(service="svc", outcome="breach avoided"))
    led.record(_case(service="svc", outcome="breach avoided"))
    assert proven_saves_for("svc", led) == 2
    assert decide(cfg, "svc", led).may_act


settings.register_profile("default", max_examples=40)
settings.load_profile("default")
