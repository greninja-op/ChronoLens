"""Unit tests for the SigNoz MCP client and the co-pilot's tool routing.

No network: the transport is stubbed so protocol handling (SSE frames, nested
JSON-in-text results, error shapes) is tested deterministically.
"""
from __future__ import annotations

import json

import pytest

from chronolens.config import Config
from chronolens.copilot import classify_intent, plan_for, summarise
from chronolens.mcp import MCPClient, MCPError, MCPResult, _parse_rpc


# ── transport parsing ─────────────────────────────────────────────────────
class _Resp:
    def __init__(self, body: str, ctype: str = "application/json", status: int = 200):
        self.text = body
        self.headers = {"content-type": ctype}
        self.status_code = status


def test_parses_plain_json_reply():
    out = _parse_rpc(_Resp(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}})))
    assert out["result"] == {"ok": 1}


def test_parses_sse_framed_reply():
    """The Streamable-HTTP transport may answer with an event-stream frame."""
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":2}}\n\n'
    out = _parse_rpc(_Resp(body, ctype="text/event-stream"))
    assert out["result"] == {"ok": 2}


def test_undecodable_body_raises():
    with pytest.raises(MCPError):
        _parse_rpc(_Resp("<html>nope</html>"))


# ── client behaviour (stubbed) ────────────────────────────────────────────
class _StubClient:
    """Stands in for httpx.Client, replaying canned JSON-RPC replies."""

    def __init__(self, replies):
        self.replies = replies
        self.sent = []

    def post(self, url, json=None):           # noqa: A002
        self.sent.append(json)
        method = json.get("method")
        body = self.replies.get(method, {"jsonrpc": "2.0", "id": json.get("id"), "result": {}})
        return _Resp(__import__("json").dumps(body))

    def close(self):
        pass


def _client(replies) -> MCPClient:
    cfg = Config.load()
    mcp = MCPClient(cfg)
    mcp._client = _StubClient(replies)     # noqa: SLF001 — deliberate injection
    return mcp


def test_handshake_sends_initialize_and_notification():
    mcp = _client({"initialize": {"jsonrpc": "2.0", "id": 1,
                                  "result": {"serverInfo": {"name": "SigNozMCP", "version": "dev"}}}})
    info = mcp.connect()
    assert info["name"] == "SigNozMCP"
    methods = [m.get("method") for m in mcp._client.sent]   # noqa: SLF001
    assert methods[0] == "initialize"
    assert "notifications/initialized" in methods
    # connect() is idempotent — no second handshake
    mcp.connect()
    assert methods.count("initialize") == 1


def test_tool_call_decodes_json_inside_a_text_block():
    """MCP returns tool payloads as JSON *inside* content[].text."""
    payload = {"data": [{"serviceName": "chronolens-store", "p99": 500_000_000}]}
    mcp = _client({
        "initialize": {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "SigNozMCP"}}},
        "tools/call": {"jsonrpc": "2.0", "id": 2,
                       "result": {"content": [{"type": "text", "text": json.dumps(payload)}]}},
    })
    res = mcp.call("signoz_list_services", {"timeRange": "30m"})
    assert res.ok
    assert res.data == payload
    assert res.arguments == {"timeRange": "30m"}


def test_tool_error_is_reported_not_raised():
    mcp = _client({
        "initialize": {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}}},
        "tools/call": {"jsonrpc": "2.0", "id": 2,
                       "result": {"isError": True,
                                  "content": [{"type": "text", "text": "bad arguments"}]}},
    })
    res = mcp.call("signoz_search_logs")
    assert res.ok is False
    assert "bad arguments" in res.error


def test_rpc_error_object_is_reported_not_raised():
    mcp = _client({
        "initialize": {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}}},
        "tools/call": {"jsonrpc": "2.0", "id": 2, "error": {"message": "unknown tool"}},
    })
    res = mcp.call("nope")
    assert res.ok is False
    assert "unknown tool" in res.error


# ── co-pilot routing: the question must actually decide the tool ───────────
@pytest.mark.parametrize("question,intent", [
    ("which services are slowest right now?", "latency"),
    ("what is p99 on checkout", "latency"),
    ("are any alerts firing?", "alerts"),
    ("show me errors in the last hour", "errors"),
    ("any error logs?", "logs"),
    ("list my dashboards", "dashboards"),
    ("top operations for chronolens-store", "operations"),
    ("what metrics do we have", "metrics"),
])
def test_intent_routing_follows_the_question(question, intent):
    assert classify_intent(question) == intent


def test_plan_maps_intent_to_real_signoz_mcp_tools():
    """Every planned tool must be a real SigNoz MCP tool name."""
    real = {
        "signoz_list_services", "signoz_list_alert_rules", "signoz_search_traces",
        "signoz_search_logs", "signoz_list_dashboards", "signoz_list_metrics",
        "signoz_get_service_top_operations",
    }
    for intent in ("services", "latency", "alerts", "errors", "logs", "traces",
                   "dashboards", "metrics", "operations"):
        for tool, _args in plan_for(intent):
            assert tool in real, f"{intent} planned an unknown tool: {tool}"


def test_named_service_is_threaded_into_the_tool_arguments():
    calls = plan_for("errors", "show errors for chronolens-payments-db")
    assert calls[0][1].get("service") == "chronolens-payments-db"


def test_summary_reports_slo_breach_from_real_row_shape():
    res = MCPResult(tool="signoz_list_services", ok=True, data={"data": [
        {"serviceName": "chronolens-store", "p99": 900_000_000},      # 900ms
        {"serviceName": "chronolens-payments", "p99": 120_000_000},   # 120ms
    ]})
    text = summarise("latency", [res], slo_ms=500.0)
    assert "chronolens-store" in text
    assert "900ms" in text
    assert "over SLO" in text


def test_summary_is_honest_when_every_call_failed():
    res = MCPResult(tool="signoz_list_services", ok=False, error="boom")
    assert "failed" in summarise("services", [res], slo_ms=500.0).lower()
