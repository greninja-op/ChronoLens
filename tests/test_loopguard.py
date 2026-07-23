"""Unit tests for the agent loop / cost-spiral breaker."""
from __future__ import annotations

from chronolens.loopguard import evaluate


def test_normal_turn_is_not_a_loop():
    v = evaluate(steps=2, tools=["get_menu", "place_order"], cost_usd=0.001,
                 max_steps=6, cost_budget=0.05, repeat_threshold=4)
    assert not v.looping and v.saved_usd == 0.0


def test_repeated_tool_is_a_loop():
    v = evaluate(steps=10, tools=["get_menu"] * 10, cost_usd=0.02,
                 max_steps=6, cost_budget=0.05, repeat_threshold=4)
    assert v.looping
    assert v.dominant_tool == "get_menu" and v.dominant_frac == 1.0
    assert v.break_at_step is not None and v.saved_usd > 0


def test_cost_budget_trips_the_breaker():
    v = evaluate(steps=5, tools=["a", "b", "c", "d", "e"], cost_usd=0.20,
                 max_steps=20, cost_budget=0.05, repeat_threshold=99)
    assert v.looping and "budget" in v.reason


def test_step_ceiling_trips_on_low_variety_cycle():
    # a,b,c cycling 12 steps: over the ceiling, low variety -> stuck cyclic loop
    v = evaluate(steps=12, tools=["a", "b", "c"] * 4, cost_usd=0.01,
                 max_steps=6, cost_budget=1.0, repeat_threshold=99)
    assert v.looping and "ceiling" in v.reason


def test_long_but_productive_turn_is_allowed():
    # many DIFFERENT tools, no single one dominates -> productive, not stuck
    tools = ["search", "read", "summarize", "translate", "verify", "format", "rank"]
    v = evaluate(steps=len(tools), tools=tools, cost_usd=0.01,
                 max_steps=6, cost_budget=0.05, repeat_threshold=4)
    assert not v.looping
    assert "productive" in v.reason


def test_saved_is_projected_minus_break_cost():
    v = evaluate(steps=10, tools=["x"] * 10, cost_usd=0.10,
                 max_steps=6, cost_budget=1.0, repeat_threshold=4)
    # per-step 0.01, break at 4 -> cost_at_break 0.04, saved ~0.06
    assert v.break_at_step == 4
    assert abs(v.saved_usd - 0.06) < 1e-6
