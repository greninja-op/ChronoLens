"""Tests for the SigNoz guard (Task 15).

On a prevented incident (managed run, outcome "breach avoided") the RECORD stage
auto-creates a guarding SigNoz alert + dashboard so the incident stays watched.

Covers:
  - guard builders produce a p99/latency alert at the SLO in **nanoseconds**
  - the dashboard latency panel carries ``yAxisUnit: "ns"``
  - RECORD triggers create_alert + create_dashboard exactly once on a managed
    "breach avoided" outcome, and NOT on baseline / healthy / escalated ones
  - a raised SigNozError during guard creation is swallowed (loop still returns)
"""
from __future__ import annotations

import pytest

from chronolens import loop as loop_mod
from chronolens.foresee import Forecast
from chronolens.learn import Memory
from chronolens.record import Ledger
from chronolens.signoz import (
    LATENCY_Y_AXIS_UNIT,
    SigNozError,
    build_guard_alert,
    build_guard_dashboard,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeSigNoz:
    """Captures create_alert / create_dashboard calls without a live SigNoz."""

    def __init__(self, *, fail_alert: bool = False, fail_dashboard: bool = False):
        self.alerts: list[dict] = []
        self.dashboards: list[dict] = []
        self._fail_alert = fail_alert
        self._fail_dashboard = fail_dashboard

    def create_alert(self, rule: dict) -> dict:
        if self._fail_alert:
            raise SigNozError("create_alert", "boom", status=500)
        self.alerts.append(rule)
        return {"data": {"id": f"alert-{len(self.alerts)}"}}

    def create_dashboard(self, dashboard: dict) -> dict:
        if self._fail_dashboard:
            raise SigNozError("create_dashboard", "boom", status=500)
        self.dashboards.append(dashboard)
        return {"data": {"id": f"dash-{len(self.dashboards)}"}}


class Cfg:
    """Config stand-in covering the knobs the loop reads."""

    def __init__(self, slo_ms: float = 500.0):
        self.p99_slo_ms = slo_ms
        self.autonomy = "auto"
        self.trust_min_saves = 3
        self.min_dwell_s = 0.0
        self.max_capacity = 12.0
        self.min_slope_ms_per_s = 3.0
        self.min_samples = 4
        self.cost_per_unit_hr = 0.65
        self.llm_provider = "none"
        self.openai_api_key = ""
        self.notify_webhook_url = ""
        self.demo_store_url = "http://localhost:8090"


def _forecast(service: str = "checkout") -> Forecast:
    return Forecast(
        service=service,
        current_p99_ms=420.0,
        slope_ms_per_s=15.0,
        seconds_to_breach=8.0,
        breaching_now=False,
        samples=[300.0, 360.0, 420.0],
    )


def _memory(service: str = "checkout") -> Memory:
    return Memory(service=service, incident_count=0, recurrence=0,
                  recommended_floor=0.0, lead_window_s=120.0, note="first")


def _run_finish(sn, *, managed: bool, outcome: str, tmp_path) -> tuple[list[dict], Ledger]:
    """Drive the RECORD stage (_finish) directly with injected doubles."""
    ledger = Ledger(root=str(tmp_path))
    timeline: list[dict] = []
    loop_mod._finish(
        ledger, "loop-1", timeline, "checkout", _forecast(), Cfg(), "onset",
        False, _memory(), managed, sn=sn,
        action="scale", rollback_txt="scale back down", verified=True,
        final_p99=380.0, peak_p99=430.0, outcome=outcome, cooldown=None,
    )
    return timeline, ledger


# --------------------------------------------------------------------------- #
# (a) alert builder — threshold at the SLO, in nanoseconds
# --------------------------------------------------------------------------- #
def test_build_guard_alert_threshold_in_nanoseconds():
    alert = build_guard_alert("checkout", 500.0)
    cond = alert["condition"]
    # SLO 500ms => 500 * 1e6 ns.
    assert cond["target"] == 500.0 * 1e6
    assert cond["targetUnit"] == "ns"
    assert cond["op"] == ">"
    # Watches p99(duration_nano) for the right service.
    q = cond["compositeQuery"]["builderQueries"]["A"]
    assert q["aggregateOperator"] == "p99"
    assert q["aggregateAttribute"]["key"] == "duration_nano"
    assert q["filters"]["items"][0]["value"] == "checkout"
    assert "checkout" in alert["alert"]


# --------------------------------------------------------------------------- #
# (b) dashboard builder — latency panel carries yAxisUnit "ns"
# --------------------------------------------------------------------------- #
def test_build_guard_dashboard_latency_panel_uses_ns():
    dash = build_guard_dashboard("checkout", 500.0)
    assert dash["widgets"], "dashboard must have at least one panel"
    panel = dash["widgets"][0]
    assert panel["yAxisUnit"] == "ns" == LATENCY_Y_AXIS_UNIT
    # Threshold marker is also in nanoseconds.
    assert panel["thresholds"][0]["value"] == 500.0 * 1e6
    assert panel["thresholds"][0]["unit"] == "ns"
    # Panel queries the same p99 latency signal for the service.
    qd = panel["query"]["builder"]["queryData"][0]
    assert qd["aggregateOperator"] == "p99"
    assert qd["aggregateAttribute"]["key"] == "duration_nano"


# --------------------------------------------------------------------------- #
# (c) RECORD triggers guard exactly once on managed "breach avoided"
# --------------------------------------------------------------------------- #
def test_record_installs_guard_once_on_breach_avoided(tmp_path):
    sn = FakeSigNoz()
    timeline, ledger = _run_finish(sn, managed=True, outcome="breach avoided",
                                   tmp_path=tmp_path)
    assert len(sn.alerts) == 1
    assert len(sn.dashboards) == 1
    # A GUARD timeline entry was filed.
    assert any(e["step"] == "GUARD" and e["status"] == "done" for e in timeline)
    # The artifact references are persisted on the case evidence.
    case = ledger.list()[-1]
    assert case["evidence"]["guard_alert"]["id"] == "alert-1"
    assert case["evidence"]["guard_dashboard"]["id"] == "dash-1"


@pytest.mark.parametrize(
    "managed, outcome",
    [
        (False, "breach avoided"),  # baseline A/B arm — no action, no guard
        (True, "healthy"),          # nothing was prevented
        (True, "pre-empted"),       # learned pre-provision, not a "breach avoided"
        (True, "escalated"),        # action didn't hold — not prevented
        (True, "watch-only"),
    ],
)
def test_record_does_not_install_guard_otherwise(tmp_path, managed, outcome):
    sn = FakeSigNoz()
    timeline, _ = _run_finish(sn, managed=managed, outcome=outcome, tmp_path=tmp_path)
    assert sn.alerts == []
    assert sn.dashboards == []
    assert not any(e["step"] == "GUARD" for e in timeline)


# --------------------------------------------------------------------------- #
# (d) SigNozError during guard creation is swallowed
# --------------------------------------------------------------------------- #
def test_guard_signoz_error_is_swallowed(tmp_path):
    sn = FakeSigNoz(fail_alert=True)
    # Must not raise, and the case file must still be recorded (RECORD proceeds).
    timeline, ledger = _run_finish(sn, managed=True, outcome="breach avoided",
                                   tmp_path=tmp_path)
    assert ledger.total_count() == 1
    guard_entries = [e for e in timeline if e["step"] == "GUARD"]
    assert guard_entries and guard_entries[0]["status"] == "info"
    assert any(e["step"] == "RECORD" for e in timeline)


def test_guard_dashboard_failure_is_swallowed(tmp_path):
    sn = FakeSigNoz(fail_dashboard=True)
    timeline, ledger = _run_finish(sn, managed=True, outcome="breach avoided",
                                   tmp_path=tmp_path)
    assert ledger.total_count() == 1
    # Alert was created before the dashboard failed; failure is downgraded.
    assert len(sn.alerts) == 1
    assert any(e["step"] == "GUARD" and e["status"] == "info" for e in timeline)


# --------------------------------------------------------------------------- #
# run_loop-level: a guard failure never crashes the loop (it still returns)
# --------------------------------------------------------------------------- #
def test_run_loop_returns_even_when_guard_fails(tmp_path, monkeypatch):
    from chronolens.cooldown import CoolDown
    from chronolens.prevent import Remediation
    from chronolens.verify import Verification

    fc = _forecast()

    monkeypatch.setattr(loop_mod, "worst_service", lambda sn, cfg, **kw: fc)
    monkeypatch.setattr(loop_mod, "recall", lambda svc, ledger: _memory())
    monkeypatch.setattr(loop_mod, "predict_blast_path",
                        lambda entry: type("B", (), {"narrative": "n", "root": "db"})())
    monkeypatch.setattr(loop_mod, "propose",
                        lambda svc, cfg=None, **kw: Remediation(
                            action="scale", params={"service": svc, "value": 2.0},
                            rollback="down", signal="load", why="load rising"))
    monkeypatch.setattr(loop_mod, "apply",
                        lambda cfg, rem: (setattr(rem, "applied", True) or rem))
    monkeypatch.setattr(loop_mod, "verify",
                        lambda sn, svc, slo: Verification(True, 380.0, 430.0, [430.0, 380.0]))
    monkeypatch.setattr(loop_mod, "cool_down",
                        lambda cfg: CoolDown(False, 4, 4, 0, 0, "held"))

    sn = FakeSigNoz(fail_alert=True)  # guard blows up mid-loop
    ledger = Ledger(root=str(tmp_path))

    result = loop_mod.run_loop(sn, Cfg(), managed=True, ledger=ledger)

    assert result["outcome"] == "breach avoided"
    assert ledger.total_count() == 1  # loop completed and recorded despite guard failure
