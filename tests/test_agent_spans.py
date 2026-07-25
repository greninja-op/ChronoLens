"""Agent Watch reading from SigNoz: GenAI span query + row parsing (no network)."""
from __future__ import annotations

from chronolens.signoz import (
    AGENT_TURN_FIELDS,
    build_agent_turns_query,
    parse_agent_turn_rows,
)


# --------------------------------------------------------------------------- #
# query shape
# --------------------------------------------------------------------------- #
def test_query_is_a_raw_traces_query_filtered_to_turn_spans():
    q = build_agent_turns_query("chronolens-agent", window_seconds=600, limit=25)
    assert q["requestType"] == "raw"
    spec = q["compositeQuery"]["queries"][0]["spec"]
    assert spec["signal"] == "traces"
    assert "service.name = 'chronolens-agent'" in spec["filter"]["expression"]
    assert "name = 'agent.turn'" in spec["filter"]["expression"]
    assert spec["limit"] == 25


def test_query_selects_the_genai_attributes_the_analyzers_need():
    q = build_agent_turns_query("a")
    selected = {f["name"] for f in q["compositeQuery"]["queries"][0]["spec"]["selectFields"]}
    assert selected == set(AGENT_TURN_FIELDS)
    for needed in ("llm.cost_usd", "llm.step_count", "agent.tools", "gen_ai.request.model"):
        assert needed in selected


def test_query_window_is_bounded_and_ordered_newest_first():
    q = build_agent_turns_query("a", window_seconds=300)
    assert q["end"] - q["start"] == 300 * 1000
    order = q["compositeQuery"]["queries"][0]["spec"]["order"][0]
    assert order["direction"] == "desc"


# --------------------------------------------------------------------------- #
# row parsing — v5 wraps rows differently across versions
# --------------------------------------------------------------------------- #
def _row(tools="get_menu,place_order", steps=2, cost=0.0004, model="gpt-4o-mini",
         looping="false", out_tok=150):
    return {
        "gen_ai.request.model": model,
        "gen_ai.usage.input_tokens": "120",
        "gen_ai.usage.output_tokens": str(out_tok),
        "llm.step_count": str(steps),
        "llm.cost_usd": str(cost),
        "agent.tools": tools,
        "agent.looping": looping,
    }


def test_parses_rows_from_data_wrapper():
    turns = parse_agent_turn_rows({"data": [_row(), _row()]})
    assert len(turns) == 2
    t = turns[0]
    assert t["tools"] == ["get_menu", "place_order"]
    assert t["steps"] == 2
    assert t["cost_usd"] == 0.0004
    assert t["model"] == "gpt-4o-mini"
    assert t["looping"] is False
    assert t["source"] == "signoz"


def test_parses_rows_from_nested_result_rows_wrapper():
    body = {"data": {"result": [{"rows": [_row(), _row(), _row()]}]}}
    assert len(parse_agent_turn_rows(body)) == 3


def test_parses_rows_nested_under_attributes():
    body = {"data": [{"timestamp": 1, "attributes": _row()}]}
    turns = parse_agent_turn_rows(body)
    assert len(turns) == 1
    assert turns[0]["steps"] == 2


def test_looping_flag_and_repeated_tools_survive():
    turns = parse_agent_turn_rows({"data": [_row(tools=",".join(["get_menu"] * 11),
                                                 steps=11, cost=0.09, looping="true")]})
    t = turns[0]
    assert t["looping"] is True
    assert len(t["tools"]) == 11
    assert t["steps"] == 11
    assert t["cost_usd"] == 0.09


def test_steps_fall_back_to_tool_count_when_absent():
    row = _row()
    del row["llm.step_count"]
    turns = parse_agent_turn_rows({"data": [row]})
    assert turns[0]["steps"] == 2


def test_malformed_numbers_do_not_raise():
    row = _row()
    row["llm.cost_usd"] = "not-a-number"
    row["gen_ai.usage.output_tokens"] = None
    turns = parse_agent_turn_rows({"data": [row]})
    assert turns[0]["cost_usd"] == 0.0
    assert turns[0]["output_tokens"] == 0


def test_empty_or_unexpected_payloads_return_empty():
    for body in ({}, {"data": []}, {"data": None}, {"status": "ok"}, []):
        assert parse_agent_turn_rows(body) == []


# --------------------------------------------------------------------------- #
# the parsed turns must be directly usable by the existing analyzers
# --------------------------------------------------------------------------- #
def test_parsed_turns_feed_the_loop_breaker():
    from chronolens.loopguard import evaluate
    turns = parse_agent_turn_rows({"data": [_row(tools=",".join(["get_menu"] * 12),
                                                 steps=12, cost=0.12)]})
    t = turns[0]
    v = evaluate(t["steps"], t["tools"], t["cost_usd"],
                 max_steps=6, cost_budget=0.05, repeat_threshold=4)
    assert v.looping is True
    assert v.dominant_tool == "get_menu"


def test_parsed_turns_feed_the_drift_fingerprint():
    from chronolens.drift import drift_score, fingerprint
    base = parse_agent_turn_rows({"data": [_row() for _ in range(6)]})
    drifted = parse_agent_turn_rows({"data": [
        _row(tools="web_search,get_menu,place_order", steps=3,
             model="gpt-4o", out_tok=520) for _ in range(6)]})
    d = drift_score(fingerprint(base), fingerprint(drifted), threshold=0.35)
    assert d.drifted is True
    assert any("web_search" in c for c in d.changes)
