"""Unit tests for tool circuit breaking, prompt steerage, and SigNoz GenAI span reading."""
from __future__ import annotations

import time
from chronolens.steerage import (
    ToolCircuitBreaker,
    build_steerage_prompt,
    steer_agent_context,
)


def test_tool_circuit_breaker_opens_on_failures():
    tb = ToolCircuitBreaker(failure_threshold=2, latency_threshold_ms=1000.0)
    assert tb.is_tool_available("search_store") is True

    # Record 2 failures/slow calls
    tb.record_call("search_store", latency_ms=1500.0, success=False)
    tb.record_call("search_store", latency_ms=1500.0, success=False)

    assert tb.is_tool_available("search_store") is False
    status = tb.get_status()
    assert status["search_store"]["is_open"] is True
    assert status["search_store"]["failures"] == 2


def test_steerage_prompt_generation_and_injection():
    prompt = build_steerage_prompt("web_search", reason="degraded")
    assert "web_search" in prompt
    assert "Do NOT execute 'web_search'" in prompt

    messages = [{"role": "user", "content": "Help me find a coffee bean"}]
    updated = steer_agent_context(messages, "web_search", reason="degraded")
    assert len(updated) == 2
    assert updated[-1]["role"] == "system"
    assert "web_search" in updated[-1]["content"]


def test_signoz_query_agent_spans(monkeypatch):
    from chronolens.signoz import SigNozClient
    
    class FakeSigNozClient(SigNozClient):
        def __init__(self):
            pass
        def query_range(self, q):
            return {
                "data": {
                    "data": {
                        "results": [
                            {
                                "columns": [{"columnType": "group"}, {"columnType": "aggregation"}],
                                "data": [["search_store", 5.0]]
                            }
                        ]
                    }
                }
            }

    client = FakeSigNozClient()
    res = client.query_agent_spans("cafe-agent")
    assert res.get("search_store") == 5.0
