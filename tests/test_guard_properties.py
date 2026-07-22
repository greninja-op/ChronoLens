"""Property-based tests for the SigNoz guard builders (Task 15).

Property (latency-in-nanoseconds invariant):
    For any SLO expressed in milliseconds, the guard alert threshold and the
    guard dashboard latency-panel threshold are both exactly ``slo_ms * 1e6``
    nanoseconds, and the latency panel always declares ``yAxisUnit = "ns"``.

**Validates: Requirements 8.2**
"""
from __future__ import annotations

import pytest

try:
    from hypothesis import given
    from hypothesis import strategies as st
except Exception:  # pragma: no cover - environment-dependent
    pytest.skip("hypothesis unavailable in this environment", allow_module_level=True)

from chronolens.signoz import build_guard_alert, build_guard_dashboard

# Plausible SLO range in milliseconds (sub-millisecond up to ~2.7 hours).
slo_ms_strategy = st.floats(
    min_value=0.001, max_value=1e7, allow_nan=False, allow_infinity=False
)


@given(slo_ms=slo_ms_strategy)
def test_alert_threshold_is_slo_in_ms(slo_ms):
    alert = build_guard_alert("svc", slo_ms, channels=["sink"])
    thr = alert["condition"]["thresholds"]["spec"][0]
    # Threshold carries the SLO in ms; SigNoz converts to duration_nano.
    assert thr["target"] == slo_ms
    assert thr["targetUnit"] == "ms"
    assert alert["condition"]["compositeQuery"]["unit"] == "ns"


@given(slo_ms=slo_ms_strategy)
def test_dashboard_latency_panel_is_ns(slo_ms):
    dash = build_guard_dashboard("svc", slo_ms)
    panel = dash["widgets"][0]
    assert panel["yAxisUnit"] == "ns"
    assert panel["thresholds"][0]["value"] == slo_ms * 1e6
    assert panel["thresholds"][0]["unit"] == "ns"
