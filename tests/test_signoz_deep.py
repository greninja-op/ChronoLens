"""Tests for the deeper SigNoz integration:

- logs query (CLASSIFY corroboration)
- span-breakdown query + data-driven CASCADE root
- alert silences around remediation (loop lifecycle)
- alert-history recurrence signal (LEARN)
- saved view + metrics-readback dashboard panel
- the grouped-series response parser
"""
from __future__ import annotations

from chronolens import loop as loop_mod
from chronolens.cascade import predict_blast_path
from chronolens.foresee import Forecast
from chronolens.learn import Memory
from chronolens.record import Ledger
from chronolens.signoz import (
    SigNozClient,
    build_guard_dashboard,
    build_guard_saved_view,
    build_guard_silence,
    build_log_query,
    build_span_breakdown_query,
    _series_by_group,
)


# --------------------------------------------------------------------------- #
# query / body builders
# --------------------------------------------------------------------------- #
def test_log_query_targets_service_and_severity():
    q = build_log_query("checkout", severity="ERROR")
    spec = q["compositeQuery"]["queries"][0]["spec"]
    assert spec["signal"] == "logs"
    assert spec["aggregations"] == [{"expression": "count()"}]
    assert "checkout" in spec["filter"]["expression"]
    assert "ERROR" in spec["filter"]["expression"]


def test_span_breakdown_groups_by_span_name():
    q = build_span_breakdown_query("checkout")
    spec = q["compositeQuery"]["queries"][0]["spec"]
    assert spec["aggregations"] == [{"expression": "p99(duration_nano)"}]
    assert spec["groupBy"] == [{"name": "name", "fieldContext": "span"}]


def test_guard_silence_matches_service():
    s = build_guard_silence("checkout", 5)
    names = {m["name"]: m["value"] for m in s["matchers"]}
    assert names["service"] == "checkout" and names["chronolens"] == "guard"
    assert s["startsAt"] and s["endsAt"] and s["createdBy"] == "chronolens"


def test_guard_saved_view_is_traces_scoped():
    v = build_guard_saved_view("checkout")
    assert v["sourcePage"] == "traces"
    spec = v["compositeQuery"]["queries"][0]["spec"]
    assert "checkout" in spec["filter"]["expression"]


def test_guard_dashboard_has_metrics_readback_panel():
    dash = build_guard_dashboard("checkout", 500.0)
    assert len(dash["widgets"]) == 2
    impact = dash["widgets"][1]
    qd = impact["query"]["builder"]["queryData"][0]
    assert qd["dataSource"] == "metrics"
    assert qd["aggregateAttribute"]["key"] == "chronolens.prevented_total"


# --------------------------------------------------------------------------- #
# grouped-series parser
# --------------------------------------------------------------------------- #
def test_series_by_group_parses_labels_and_values():
    body = {"data": {"result": [
        {"metric": "payment.db_query", "values": [[1, 1200.0]]},
        {"metric": "cart.lookup", "values": [[1, 40.0]]},
    ]}}
    got = _series_by_group(body)
    assert got.get("payment.db_query") == 1200.0
    assert got.get("cart.lookup") == 40.0


def test_series_by_group_tolerates_garbage():
    assert _series_by_group(None) == {}
    assert _series_by_group({"nonsense": 1}) == {}


# --------------------------------------------------------------------------- #
# data-driven CASCADE
# --------------------------------------------------------------------------- #
def test_cascade_uses_measured_slowest_span_as_root():
    breakdown = {"cart.lookup": 40.0, "payment.db_query": 1200.0, "order.db_write": 90.0}
    blast = predict_blast_path("/order", breakdown)
    assert blast.source == "traces"
    assert blast.root == "payment.db_query"
    assert "1200.0ms" in blast.narrative


def test_cascade_falls_back_to_static_topology():
    blast = predict_blast_path("/order", None)
    assert blast.source == "topology"
    assert blast.root  # a static root hop is named


def test_cascade_ignores_empty_breakdown():
    blast = predict_blast_path("/order", {})
    assert blast.source == "topology"


# --------------------------------------------------------------------------- #
# alert-history recurrence signal (LEARN)
# --------------------------------------------------------------------------- #
class _RulesStub:
    def __init__(self, rules):
        self._rules = rules

    def list_rules(self):
        return self._rules


def test_alert_fired_count_matches_guard_rules_that_are_firing():
    rules = [
        {"labels": {"chronolens": "guard", "service": "checkout"}, "state": "firing"},
        {"labels": {"chronolens": "guard", "service": "checkout"}, "state": "inactive"},
        {"labels": {"chronolens": "guard", "service": "other"}, "state": "firing"},
        {"labels": {"severity": "warning"}, "state": "firing"},  # not ours
    ]
    n = SigNozClient.alert_fired_count(_RulesStub(rules), "checkout")
    assert n == 1


# --------------------------------------------------------------------------- #
# silence lifecycle inside the loop
# --------------------------------------------------------------------------- #
class FullFakeSN:
    """Fake SigNoz implementing every read/write the loop touches."""

    def __init__(self):
        self.silences_created = 0
        self.silences_deleted = []
        self.alerts = []
        self.dashboards = []
        self.views = []

    # reads used via _safe
    def error_log_count(self, svc, **kw):
        return 3.0

    def span_p99_breakdown(self, svc, **kw):
        return {"cart.lookup": 40.0, "payment.db_query": 900.0}

    def exemplar_trace_id(self, svc, **kw):
        return "abc123"

    def alert_fired_count(self, svc):
        return 0

    # silence lifecycle
    def create_silence(self, svc, minutes=5):
        self.silences_created += 1
        return {"data": {"silenceId": "sil-1"}}

    def delete_silence(self, sid):
        self.silences_deleted.append(sid)
        return {}

    # guard writes
    def create_alert(self, rule):
        self.alerts.append(rule)
        return {"data": {"id": f"alert-{len(self.alerts)}"}}

    def create_dashboard(self, dash):
        self.dashboards.append(dash)
        return {"data": {"id": f"dash-{len(self.dashboards)}"}}

    def create_saved_view(self, view):
        self.views.append(view)
        return {"data": {"id": f"view-{len(self.views)}"}}


class Cfg:
    def __init__(self):
        self.p99_slo_ms = 500.0
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


def _fc():
    return Forecast("checkout", 420.0, 15.0, 8.0, False,
                    [300.0, 360.0, 420.0], confidence=0.9, confident=True)


def test_loop_silences_then_lifts_and_records_evidence(tmp_path, monkeypatch):
    from chronolens.cooldown import CoolDown
    from chronolens.prevent import Remediation
    from chronolens.verify import Verification

    monkeypatch.setattr(loop_mod, "worst_service", lambda sn, cfg, **kw: _fc())
    monkeypatch.setattr(loop_mod, "recall", lambda svc, ledger: Memory(
        svc, 0, 0, 0.0, 120.0, "first"))
    monkeypatch.setattr(loop_mod, "propose", lambda svc, cfg=None, **kw: Remediation(
        action="scale", params={"service": svc, "value": 2.0}, rollback="down",
        signal="load", why="load rising", applied=False))
    monkeypatch.setattr(loop_mod, "apply",
                        lambda cfg, rem: (setattr(rem, "applied", True) or rem))
    monkeypatch.setattr(loop_mod, "verify",
                        lambda sn, svc, slo: Verification(True, 380.0, 430.0, [430.0, 380.0]))
    monkeypatch.setattr(loop_mod, "cool_down",
                        lambda cfg: CoolDown(True, 4, 2, 2, 0, "scaled down"))

    sn = FullFakeSN()
    ledger = Ledger(root=str(tmp_path))
    result = loop_mod.run_loop(sn, Cfg(), managed=True, ledger=ledger)

    assert result["outcome"] == "breach avoided"
    # silence was created before the fix and lifted after grading
    assert sn.silences_created == 1
    assert sn.silences_deleted == ["sil-1"]
    # a saved view was filed with the guard
    assert len(sn.views) == 1
    # evidence captured the data-driven cascade + trace + silence
    case = ledger.list()[-1]
    ev = case["evidence"]
    assert ev["cascade_source"] == "traces"
    assert ev["exemplar_trace_id"] == "abc123"
    assert ev["silence_id"] == "sil-1"
    assert ev["error_logs"] == 3.0
    # timeline shows the SILENCE step both muting and lifting
    steps = [e["step"] for e in result["timeline"]]
    assert steps.count("SILENCE") == 2
