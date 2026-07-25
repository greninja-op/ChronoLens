"""Unit & Property-based tests for the 5 Breakthrough Innovations in ChronoLens:

1. Chrono-Replay Counterfactual Timelines (foresee.py)
2. Dynamic LLM Agent Context & Token Throttling (loopguard.py)
3. SigNoz MCP Natural Language Incident Co-Pilot (copilot.py)
4. Self-Calibrating Chaos & Guardrail Auto-Tuning (stress.py)
5. Executive CFO SLA ROI & Penalty Calculator (dollars.py)
"""
from __future__ import annotations

import sys
import os
from hypothesis import given, strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chronolens.config import Config
from chronolens.foresee import generate_counterfactual_projection
from chronolens.loopguard import apply_dynamic_throttle, get_throttle_status, record_throttled_turn
from chronolens.copilot import ask_signoz_copilot
from chronolens.stress import run_self_tuning_calibration, get_calibration_history
from chronolens.dollars import calculate_sla_penalty_avoided, build_executive_cfo_report


# --------------------------------------------------------------------------- #
# 1. Chrono-Replay Counterfactual Projection Tests
# --------------------------------------------------------------------------- #
def test_counterfactual_projection_basic():
    res = generate_counterfactual_projection("checkout-service", current_p99_ms=480.0, slo_ms=500.0)
    assert res["service"] == "checkout-service"
    assert res["slo_ms"] == 500.0
    assert len(res["labels"]) == 15
    assert len(res["timeline_a_unmitigated"]) == 15
    assert len(res["timeline_b_defused"]) == 15
    assert res["unmitigated_breach_duration_s"] > 0
    assert res["defused_breach_duration_s"] == 0
    assert res["prevention_success"] is True


@given(p99=st.floats(min_value=100.0, max_value=800.0), slope=st.floats(min_value=1.0, max_value=50.0))
def test_counterfactual_projection_property(p99: float, slope: float):
    res = generate_counterfactual_projection("test-service", current_p99_ms=p99, slope_ms_per_s=slope)
    assert len(res["timeline_a_unmitigated"]) == len(res["timeline_b_defused"])
    # Defused timeline should remain bounded below max unmitigated surge
    assert max(res["timeline_b_defused"]) <= max(res["timeline_a_unmitigated"]) + 100.0


# --------------------------------------------------------------------------- #
# 2. Dynamic Token Circuit-Breaker Tests
# --------------------------------------------------------------------------- #
def test_agent_token_throttling_state():
    apply_dynamic_throttle(enabled=True, max_tokens=256, force_fallback_model=True)
    status = get_throttle_status()
    assert status["enabled"] is True
    assert status["max_tokens"] == 256
    assert status["force_fallback_model"] is True

    record_res = record_throttled_turn(tokens_saved=200)
    assert record_res["throttled_turn_count"] >= 1
    assert record_res["saved_tokens_total"] >= 200

    # Reset state
    apply_dynamic_throttle(enabled=False)
    assert get_throttle_status()["enabled"] is False


@given(max_tok=st.integers(min_value=64, max_value=1024), saved=st.integers(min_value=0, max_value=5000))
def test_token_throttling_property(max_tok: int, saved: int):
    st_res = apply_dynamic_throttle(enabled=True, max_tokens=max_tok)
    assert st_res["max_tokens"] == max_tok
    rec = record_throttled_turn(tokens_saved=saved)
    assert rec["saved_tokens_total"] >= saved


# --------------------------------------------------------------------------- #
# 3. SigNoz MCP Co-Pilot Tests
# --------------------------------------------------------------------------- #
def test_signoz_mcp_copilot_diagnosis():
    cfg = Config.load()
    res = ask_signoz_copilot("Why did payment-service degrade?", cfg)
    assert "query" in res
    assert "answer" in res
    assert "signoz_deep_link" in res
    assert res["mcp_query_type"] == "builder_v5_traces_logs"
    assert "evidence" in res
    assert "trace_id_exemplar" in res["evidence"]


# --------------------------------------------------------------------------- #
# 4. Self-Calibrating Chaos Tuning Tests
# --------------------------------------------------------------------------- #
def test_stress_tuning_calibration():
    cfg = Config.load()
    initial_slope = cfg.min_slope_ms_per_s
    initial_dwell = cfg.min_dwell_s


    res = run_self_tuning_calibration(cfg, service_name="checkout-service")
    assert "calibration_id" in res
    assert "tuning" in res
    assert res["detection_latency_ms"] > 0
    assert res["status"] in ("OPTIMAL", "CALIBRATED")

    history = get_calibration_history()
    assert len(history) >= 1
    assert history[-1]["service"] == "checkout-service"


# --------------------------------------------------------------------------- #
# 5. Executive CFO ROI & SLA Penalty Tests
# --------------------------------------------------------------------------- #
def test_cfo_sla_penalty_calculator():
    metrics = calculate_sla_penalty_avoided(prevented_incidents_count=4, avg_outage_min_per_incident=10.0, sla_penalty_per_outage_min=200.0)
    assert metrics["prevented_incidents"] == 4
    assert metrics["outage_minutes_saved"] == 40.0
    assert metrics["total_sla_penalty_avoided_usd"] == 8000.0


def test_build_executive_cfo_report():
    cfg = Config.load()
    dummy_ledger = [
        {"cost_saved_usd": 12.50, "service": "checkout-service"},
        {"cost_saved_usd": 8.00, "service": "payment-service"},
    ]
    report = build_executive_cfo_report(ledger_records=dummy_ledger, cfg=cfg, sla_rate_per_min=250.0)
    assert report["prevented_incidents"] == 2
    assert report["compute_cost_saved_usd"] == 20.50
    assert report["sla_penalty_avoided_usd"] > 0
    assert report["total_financial_roi_usd"] > 20.50
    assert "# Executive Reliability & Financial ROI Report" in report["report_markdown"]
    assert "Total Net Financial ROI" in report["report_markdown"]

