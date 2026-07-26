"""SigNoz client for ChronoLens.

Reads go through the SigNoz **Query Builder v5** (`POST /api/v5/query_range`),
the same query shape the SigNoz MCP server executes — so the read layer is
MCP-compatible. Writes create alert rules and dashboards. Every call is wrapped
so a SigNoz hiccup surfaces cleanly instead of killing the loop.

Endpoints (SigNoz v0.x):
  POST /api/v2/services       service RED stats (nanosecond string times)
  POST /api/v5/query_range    Query Builder v5 reads
  POST /api/v2/rules          create alert rule
  POST /api/v1/dashboards     create dashboard
  GET/POST /api/v1/channels   notification channels
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from .config import Config


def _now_ns() -> int:
    return time.time_ns()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class SigNozError(Exception):
    def __init__(self, operation: str, message: str, status: int | None = None):
        self.operation = operation
        self.status = status
        detail = f" (status {status})" if status is not None else ""
        super().__init__(f"SigNoz '{operation}' failed{detail}: {message}")


def build_trace_query(
    filter_expression: str,
    aggregations: list[dict[str, Any]],
    *,
    window_seconds: int = 300,
    step_interval: int = 30,
    group_by: list[dict[str, Any]] | None = None,
    request_type: str = "time_series",
) -> dict[str, Any]:
    """Build a Query Builder v5 traces envelope (MCP-compatible shape)."""
    end = _now_ms()
    start = end - window_seconds * 1000
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": request_type,
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "traces",
                        "stepInterval": step_interval,
                        "aggregations": aggregations,
                        "filter": {"expression": filter_expression},
                        "groupBy": group_by or [],
                    },
                }
            ],
        },
    }


# SigNoz stores span durations in nanoseconds, so every latency artifact we
# create (alert thresholds, dashboard axes) is expressed in ns.
LATENCY_Y_AXIS_UNIT = "ns"


def _slo_ns(slo_ms: float) -> float:
    """Convert an SLO expressed in milliseconds to nanoseconds (SigNoz native)."""
    return float(slo_ms) * 1e6


def _p99_latency_builder_query(service: str) -> dict[str, Any]:
    """A Query Builder p99(duration_nano) traces query scoped to one service.

    Shared by the guard alert and the guard dashboard so both watch exactly the
    same signal the loop forecasts on.
    """
    return {
        "queryName": "A",
        "expression": "A",
        "dataSource": "traces",
        "aggregateOperator": "p99",
        "aggregateAttribute": {"key": "duration_nano", "dataType": "float64", "type": ""},
        "filters": {
            "op": "AND",
            "items": [
                {
                    "key": {"key": "service.name", "dataType": "string", "type": "resource"},
                    "op": "=",
                    "value": service,
                }
            ],
        },
        "groupBy": [],
        "disabled": False,
        "stepInterval": 60,
    }


def _p99_traces_spec(service: str) -> dict[str, Any]:
    """Query Builder v5 spec: p99(duration_nano) for one service (traces)."""
    return {
        "name": "A",
        "signal": "traces",
        "source": "",
        "stepInterval": 60,
        "aggregations": [{"expression": "p99(duration_nano)"}],
        "filter": {"expression": f"service.name = '{service}'"},
        "groupBy": [],
    }


def build_guard_alert(service: str, slo_ms: float,
                      channels: list[str] | None = None) -> dict[str, Any]:
    """Build a guarding SigNoz alert rule on a service's p99 latency.

    Uses the SigNoz **v2alpha1 / v5** threshold-rule schema: a Query Builder v5
    traces query (``p99(duration_nano)``) with a threshold expressed in **ms**
    (SigNoz converts to ``duration_nano`` internally via ``targetUnit``). At
    least one notification channel is required by SigNoz.
    """
    return {
        "schemaVersion": "v2alpha1",
        "version": "v5",
        "alert": f"ChronoLens guard - {service} p99 latency",
        "alertType": "TRACES_BASED_ALERT",
        "ruleType": "threshold_rule",
        "condition": {
            "compositeQuery": {
                "queries": [{"type": "builder_query", "spec": _p99_traces_spec(service)}],
                "panelType": "graph",
                "queryType": "builder",
                "unit": LATENCY_Y_AXIS_UNIT,
            },
            "selectedQueryName": "A",
            "thresholds": {
                "kind": "basic",
                "spec": [
                    {
                        "name": "critical",
                        "target": float(slo_ms),
                        "targetUnit": "ms",
                        "recoveryTarget": None,
                        "matchType": "at_least_once",
                        "op": "above",
                        "channels": channels or [],
                    }
                ],
            },
        },
        "evaluation": {"kind": "rolling", "spec": {"evalWindow": "5m0s", "frequency": "1m0s"}},
        "notificationSettings": {"renotify": {"enabled": False, "interval": "30m"}},
        "disabled": False,
        "source": "chronolens",
        "labels": {"severity": "warning", "chronolens": "guard", "service": service},
        "annotations": {
            "summary": f"{service} p99 latency crossed the {slo_ms}ms SLO",
            "description": "Auto-filed by ChronoLens after a prevented incident.",
        },
    }


def build_guard_dashboard(service: str, slo_ms: float) -> dict[str, Any]:
    """Build a guarding SigNoz dashboard with a p99 latency panel for a service.

    The latency panel sets ``yAxisUnit = "ns"`` and marks the SLO threshold in
    nanoseconds, matching how SigNoz stores ``duration_nano``.
    """
    threshold_ns = _slo_ns(slo_ms)
    panel = {
        "title": f"{service} p99 latency (guarded at {slo_ms}ms SLO)",
        "description": "ChronoLens guard panel — p99 span duration for the service.",
        "panelTypes": "graph",
        "yAxisUnit": LATENCY_Y_AXIS_UNIT,
        "query": {
            "queryType": "builder",
            "builder": {"queryData": [_p99_latency_builder_query(service)]},
        },
        "thresholds": [
            {
                "index": "slo",
                "label": f"SLO {slo_ms}ms",
                "value": threshold_ns,
                "unit": LATENCY_Y_AXIS_UNIT,
            }
        ],
    }
    # Second panel reads back ChronoLens's OWN metric — the full-circle proof
    # that the agent's saves are visible in SigNoz, not just its ledger.
    impact_panel = {
        "title": "ChronoLens impact — incidents prevented",
        "description": "Reads back chronolens.prevented_total emitted by the loop itself.",
        "panelTypes": "graph",
        "yAxisUnit": "short",
        "query": {
            "queryType": "builder",
            "builder": {"queryData": [_metric_builder_query("chronolens.prevented_total")]},
        },
    }
    widgets, layout = _lay_out([panel, impact_panel])
    return {
        "title": f"ChronoLens guard - {service}",
        "description": (
            f"Auto-created by ChronoLens after preventing a breach on {service}. "
            f"Keeps the prevented incident watched."
        ),
        "tags": ["chronolens", "guard", service],
        "widgets": widgets,
        "layout": layout,
    }


def _lay_out(widgets: list[dict[str, Any]], *, per_row: int = 2,
             height: int = 6) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Give every widget a stable ``id`` and build the matching grid ``layout``.

    This is the difference between a dashboard that *stores* panels and one that
    *shows* them. SigNoz persists ``widgets`` happily without either field, then the
    UI renders "Welcome to your new dashboard" because it positions panels from
    ``layout`` (a react-grid spec keyed by widget id) and there was nothing to place.
    Nothing errors — you just get an empty dashboard, which is a genuinely confusing
    failure mode.

    Grid is 12 columns wide; ``per_row=2`` gives two half-width panels per row.
    """
    span = max(1, 12 // max(1, per_row))
    out_widgets: list[dict[str, Any]] = []
    layout: list[dict[str, Any]] = []
    for i, w in enumerate(widgets):
        wid = w.get("id") or str(uuid.uuid4())
        w = {**w, "id": wid}
        out_widgets.append(w)
        layout.append({
            "i": wid,
            "x": (i % per_row) * span,
            "y": (i // per_row) * height,
            "w": span,
            "h": height,
            "moved": False,
            "static": False,
        })
    return out_widgets, layout


def _agent_traces_query(agent_service: str, expression: str, *, name: str = "A",
                        group_by: list[dict] | None = None) -> dict[str, Any]:
    """A Query Builder traces query over the agent's GenAI spans."""
    return {
        "queryName": name,
        "expression": name,
        "dataSource": "traces",
        "aggregateOperator": "noop",
        "aggregations": [{"expression": expression}],
        "filter": {"expression": f"service.name = '{agent_service}'"},
        "filters": {"op": "AND", "items": []},
        "groupBy": group_by or [],
        "orderBy": [],
        "selectColumns": [],
        "functions": [],
        "disabled": False,
        "stepInterval": 60,
    }


def build_agent_dashboard(agent_service: str, *, max_steps: int = 6,
                          cost_budget: float = 0.05) -> dict[str, Any]:
    """Build a **GenAI guard dashboard** for the watched AI agent.

    The infra guard dashboard watches p99 for a service; this is its agent-side
    counterpart, built from the OTel **GenAI semantic-convention attributes** the
    agent emits (`gen_ai.usage.*`, `llm.step_count`, `llm.cost_usd`). It answers
    the questions latency dashboards can't: how much is each turn costing, is the
    agent taking more steps than it used to, and which tools is it actually calling.
    """
    tokens_panel = {
        "title": "Token usage per turn (output)",
        "description": "gen_ai.usage.output_tokens — answer length in tokens; a silent "
                       "jump here is how behaviour drift usually shows up first.",
        "panelTypes": "graph",
        "yAxisUnit": "short",
        "query": {"queryType": "builder", "builder": {"queryData": [
            _agent_traces_query(agent_service, "avg(gen_ai.usage.output_tokens)")]}},
    }
    cost_panel = {
        "title": f"Cost per turn (USD, budget ${cost_budget})",
        "description": "llm.cost_usd — real money per turn. The loop/cost breaker "
                       "fires on this budget, not on a clock.",
        "panelTypes": "graph",
        "yAxisUnit": "none",
        "query": {"queryType": "builder", "builder": {"queryData": [
            _agent_traces_query(agent_service, "avg(llm.cost_usd)")]}},
        "thresholds": [{"index": "budget", "label": f"budget ${cost_budget}",
                        "value": float(cost_budget), "unit": "none"}],
    }
    steps_panel = {
        "title": f"Steps per turn (ceiling {max_steps})",
        "description": "llm.step_count — a rising step count with no new tools is a loop.",
        "panelTypes": "graph",
        "yAxisUnit": "short",
        "query": {"queryType": "builder", "builder": {"queryData": [
            _agent_traces_query(agent_service, "max(llm.step_count)")]}},
        "thresholds": [{"index": "ceiling", "label": f"ceiling {max_steps}",
                        "value": float(max_steps), "unit": "short"}],
    }
    tools_panel = {
        "title": "Tool calls by name",
        "description": "tool.execute spans grouped by tool.name — reveals a tool the "
                       "agent never used before, or one it now calls repeatedly.",
        "panelTypes": "graph",
        "yAxisUnit": "short",
        "query": {"queryType": "builder", "builder": {"queryData": [
            _agent_traces_query(
                agent_service, "count()",
                group_by=[{"key": "tool.name", "dataType": "string", "type": "tag"}])]}},
    }
    latency_panel = {
        "title": "Turn latency p99",
        "description": "For contrast: latency can stay flat while behaviour drifts — "
                       "which is exactly why the panels above exist.",
        "panelTypes": "graph",
        "yAxisUnit": LATENCY_Y_AXIS_UNIT,
        "query": {"queryType": "builder", "builder": {"queryData": [
            _p99_latency_builder_query(agent_service)]}},
    }
    widgets, layout = _lay_out(
        [cost_panel, steps_panel, tokens_panel, tools_panel, latency_panel])
    return {
        "title": f"ChronoLens Agent Watch - {agent_service}",
        "description": (
            "Auto-created by ChronoLens. GenAI-native view of the watched agent: tokens, "
            "cost per turn, steps and tool mix — the signals that move when an agent "
            "silently changes behaviour while still returning 200 OK."
        ),
        "tags": ["chronolens", "agent-watch", "genai", agent_service],
        "widgets": widgets,
        "layout": layout,
    }


def build_agent_cost_alert(agent_service: str, cost_budget: float,
                           channels: list[str] | None = None) -> dict[str, Any]:
    """Threshold alert on the agent's **cost per turn** — a runaway-spend guard."""
    return {
        "schemaVersion": "v2alpha1",
        "version": "v5",
        "alert": f"ChronoLens guard - {agent_service} cost per turn",
        "alertType": "TRACES_BASED_ALERT",
        "ruleType": "threshold_rule",
        "condition": {
            "compositeQuery": {
                "queries": [{"type": "builder_query", "spec": {
                    "name": "A", "signal": "traces", "disabled": False,
                    "stepInterval": 60,
                    "aggregations": [{"expression": "avg(llm.cost_usd)"}],
                    "filter": {"expression": f"service.name = '{agent_service}'"},
                    "groupBy": [],
                }}],
                "panelType": "graph", "queryType": "builder", "unit": "none",
            },
            "selectedQueryName": "A",
            "thresholds": {"kind": "basic", "spec": [{
                "name": "warning",
                "target": float(cost_budget),
                "targetUnit": "none",
                "recoveryTarget": None,
                "matchType": "at_least_once",
                "op": "above",
                "channels": channels or [],
            }]},
        },
        "evaluation": {"kind": "rolling", "spec": {"evalWindow": "5m0s", "frequency": "1m0s"}},
        "notificationSettings": {"renotify": {"enabled": False, "interval": "30m"}},
        "disabled": False,
        "source": "chronolens",
        "labels": {"severity": "warning", "chronolens": "guard",
                   "guard_kind": "agent-cost", "service": agent_service},
        "annotations": {
            "summary": f"{agent_service} average cost per turn exceeded ${cost_budget}",
            "description": "Auto-filed by ChronoLens Agent Watch (runaway-spend guard).",
        },
    }


def build_anomaly_alert_mcp_args(metric_name: str = "chronolens.agent.cost_usd",
                                 channels: list[str] | None = None, *,
                                 z_score: float = 2.0,
                                 seasonality: str = "daily",
                                 label: str = "") -> dict[str, Any]:
    """Arguments for creating the anomaly rule via the **SigNoz MCP** ``signoz_create_alert``.

    Why MCP rather than our REST client: the anomaly rule uses the older v1 rule
    schema, and this SigNoz build rejects it on the REST ``/api/v2/rules`` and
    ``/api/v1/rules`` endpoints with ``validation failed`` and an *empty* error list —
    no field named, nothing to correct. The MCP server accepts the same logical rule
    and performs the version handling itself, so we let the tool own that quirk.

    It also means ChronoLens uses MCP for **writes**, not only reads.
    """
    rule = build_anomaly_alert(metric_name, channels, z_score=z_score,
                              seasonality=seasonality, label=label)
    return {
        "alert": rule["alert"],
        "alertType": rule["alertType"],
        "ruleType": rule["ruleType"],
        "evalWindow": rule["evalWindow"],
        "frequency": rule["frequency"],
        "condition": rule["condition"],
        "labels": rule["labels"],
        "annotations": rule["annotations"],
        "preferredChannels": rule.get("preferredChannels") or [],
    }


def build_anomaly_alert(metric_name: str = "chronolens.agent.cost_usd",
                        channels: list[str] | None = None, *,
                        z_score: float = 2.0,
                        seasonality: str = "daily",
                        label: str = "") -> dict[str, Any]:
    """Build an **anomaly** alert rule — a learned baseline, not a fixed threshold.

    A static SLO can't catch "normal-looking but abnormal for this hour": a metric
    that usually sits low and drifts upward may still be under its fixed limit yet
    clearly wrong. SigNoz's anomaly rules compare against a learned seasonal
    baseline instead.

    Two schema constraints, both learned the hard way against a live server:

    1. **Anomaly rules only accept ``METRIC_BASED_ALERT``.** Pointing one at a traces
       query is rejected (``anomaly_rule can only be used with METRIC_BASED_ALERT``),
       so this alerts on an emitted *metric*, not on a span aggregation.
    2. It uses the **v1 rule schema** — top-level ``evalWindow``/``frequency`` and
       ``condition.op``/``matchType``/``target``/``algorithm``/``seasonality``, with
       the ``anomaly`` function on the query. Sending the v2alpha1 threshold shape
       here fails validation with an empty error list, which is unhelpfully quiet.
    """
    subject = label or metric_name
    return {
        # `version: v5` is required even though `schemaVersion` must be omitted for
        # anomaly rules — leaving it out fails validation with an empty error list.
        "version": "v5",
        "alert": f"ChronoLens anomaly - {subject} deviates from its baseline",
        "alertType": "METRIC_BASED_ALERT",
        "ruleType": "anomaly_rule",
        "evalWindow": "5m",
        "frequency": "1m",
        "condition": {
            "compositeQuery": {
                "queries": [{"type": "builder_query", "spec": {
                    "name": "A",
                    "signal": "metrics",
                    "disabled": False,
                    "stepInterval": 60,
                    "aggregations": [{
                        "metricName": metric_name,
                        "timeAggregation": "avg",
                        "spaceAggregation": "max",
                    }],
                    "functions": [{"name": "anomaly",
                                   "args": [{"name": "z_score_threshold", "value": z_score}]}],
                }}],
                "panelType": "graph", "queryType": "builder", "unit": "none",
            },
            "selectedQueryName": "A",
            "op": "above",
            "matchType": "at_least_once",
            "target": float(z_score),
            "algorithm": "standard",
            "seasonality": seasonality,
        },
        "disabled": False,
        "source": "chronolens",
        "preferredChannels": channels or [],
        "labels": {"severity": "info", "chronolens": "guard",
                   "guard_kind": "anomaly", "metric": metric_name},
        "annotations": {
            "summary": f"{subject} is anomalous versus its {seasonality} baseline",
            "description": ("Auto-filed by ChronoLens. Catches 'abnormal for this hour' "
                            "even while still inside the fixed limit."),
        },
    }


def _metric_builder_query(metric_name: str) -> dict[str, Any]:
    """A Query Builder metrics query for one of ChronoLens's own gauges."""
    return {
        "queryName": "A",
        "expression": "A",
        "dataSource": "metrics",
        "aggregateOperator": "avg",
        "aggregateAttribute": {"key": metric_name, "dataType": "float64", "type": "Gauge"},
        "timeAggregation": "avg",
        "spaceAggregation": "max",
        "filters": {"op": "AND", "items": []},
        "groupBy": [],
        "disabled": False,
        "stepInterval": 60,
    }


def build_log_query(service: str, *, severity: str = "ERROR",
                    window_seconds: int = 120) -> dict[str, Any]:
    """Query Builder v5 LOGS query: count of severity-level logs for a service.

    Used by CLASSIFY to corroborate the 'errors' signal from a second source
    (logs) instead of trusting the trace/latency signal alone.
    """
    end = _now_ms()
    start = end - window_seconds * 1000
    expr = f"service.name = '{service}' AND severity_text = '{severity}'"
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "scalar",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "logs",
                        "stepInterval": 60,
                        "aggregations": [{"expression": "count()"}],
                        "filter": {"expression": expr},
                        "groupBy": [],
                    },
                }
            ],
        },
    }


def build_span_breakdown_query(service: str, *, window_seconds: int = 300) -> dict[str, Any]:
    """Query Builder v5 traces query: p99(duration_nano) grouped by span name.

    The slowest span name is the empirical root of the blast path — this is how
    CASCADE becomes data-driven instead of relying on a hardcoded topology.
    """
    end = _now_ms()
    start = end - window_seconds * 1000
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "scalar",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "traces",
                        "stepInterval": 60,
                        "aggregations": [{"expression": "p99(duration_nano)"}],
                        "filter": {"expression": f"service.name = '{service}'"},
                        "groupBy": [{"name": "name", "fieldContext": "span"}],
                    },
                }
            ],
        },
    }


AGENT_TURN_FIELDS = [
    "gen_ai.request.model", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "llm.step_count", "llm.cost_usd", "agent.tools", "agent.looping",
]


def build_agent_turns_query(service: str, *, window_seconds: int = 900,
                            limit: int = 50, span_name: str = "agent.turn") -> dict[str, Any]:
    """Query Builder v5 **raw** traces query for an AI agent's turn spans.

    Returns one row per agent turn carrying the OpenTelemetry GenAI attributes
    the Agent Watch analyzers need (model, token usage, step count, cost, tools).
    This is what lets drift / loop detection run off *telemetry in SigNoz* rather
    than by calling the agent directly.
    """
    end = _now_ms()
    start = end - window_seconds * 1000
    return {
        "schemaVersion": "v1",
        "start": start,
        "end": end,
        "requestType": "raw",
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "traces",
                        "filter": {"expression":
                                   f"service.name = '{service}' AND name = '{span_name}'"},
                        "selectFields": [{"name": f, "fieldContext": "attribute"}
                                         for f in AGENT_TURN_FIELDS],
                        "order": [{"key": {"name": "timestamp"}, "direction": "desc"}],
                        "limit": limit,
                    },
                }
            ],
        },
    }


def _as_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def parse_agent_turn_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize a v5 raw-traces response into the turn dicts the analyzers expect.

    Pure function so it can be tested against recorded payloads. v5 wraps rows in
    a few different containers depending on version, so walk for anything that
    looks like a row with span attributes.
    """
    rows: list[dict[str, Any]] = []

    def _collect(node: Any) -> None:
        if isinstance(node, dict):
            # a row is a dict that carries the attributes we selected
            keys = set(node.keys())
            if keys & {"agent.tools", "llm.step_count", "gen_ai.request.model"}:
                rows.append(node)
                return
            for key in ("data", "rows", "result", "results", "series", "list", "spans"):
                if key in node:
                    _collect(node[key])
            # v5 sometimes nests the attribute map one level down
            for key in ("attributes", "data", "span"):
                val = node.get(key)
                if isinstance(val, dict) and (set(val.keys()) &
                                              {"agent.tools", "llm.step_count"}):
                    rows.append(val)
        elif isinstance(node, list):
            for item in node:
                _collect(item)

    _collect(body)

    turns: list[dict[str, Any]] = []
    for r in rows:
        tools_raw = r.get("agent.tools") or ""
        tools = [t.strip() for t in str(tools_raw).split(",") if t.strip()]
        steps = int(_as_float(r.get("llm.step_count"), len(tools)))
        looping = str(r.get("agent.looping", "")).lower() in ("true", "1", "yes")
        turns.append({
            "model": r.get("gen_ai.request.model") or "",
            "tools": tools,
            "steps": steps or len(tools),
            "input_tokens": int(_as_float(r.get("gen_ai.usage.input_tokens"))),
            "output_tokens": int(_as_float(r.get("gen_ai.usage.output_tokens"))),
            "cost_usd": _as_float(r.get("llm.cost_usd")),
            "looping": looping,
            "source": "signoz",
        })
    return turns


def build_guard_silence(service: str, minutes: int, *, created_by: str = "chronolens") -> dict[str, Any]:
    """AlertManager-style silence body: mute a service's alert while the loop
    is actively remediating, so a human isn't paged for something being handled."""
    start = time.gmtime()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", start)
    end_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + minutes * 60))
    return {
        "matchers": [
            {"name": "service", "value": service, "isRegex": False, "isEqual": True},
            {"name": "chronolens", "value": "guard", "isRegex": False, "isEqual": True},
        ],
        "startsAt": start_iso,
        "endsAt": end_iso,
        "createdBy": created_by,
        "comment": f"ChronoLens is actively remediating {service}; muting during the fix.",
    }


def build_guard_saved_view(service: str) -> dict[str, Any]:
    """A saved Traces-explorer view pinned to the guarded service, so a human
    clicking through lands on the right filter."""
    return {
        "name": f"ChronoLens guard - {service}",
        "category": "chronolens",
        "sourcePage": "traces",
        "tags": ["chronolens", "guard"],
        "compositeQuery": {
            "queryType": "builder",
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "traces",
                        "aggregations": [{"expression": "p99(duration_nano)"}],
                        "filter": {"expression": f"service.name = '{service}'"},
                    },
                }
            ],
        },
    }


class SigNozClient:
    def __init__(self, cfg: Config | None = None, timeout: float = 30.0):
        self.cfg = cfg or Config.load()
        self.cfg.require_signoz()
        self._client = httpx.Client(
            base_url=self.cfg.signoz_url,
            headers={
                "SIGNOZ-API-KEY": self.cfg.signoz_api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def _post(self, operation: str, path: str, body: dict[str, Any]) -> Any:
        try:
            r = self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise SigNozError(operation, f"transport failure: {exc}") from exc
        if r.status_code >= 400:
            raise SigNozError(operation, r.text[:200], status=r.status_code)
        try:
            return r.json()
        except ValueError:
            return {}

    def _get(self, operation: str, path: str) -> Any:
        try:
            r = self._client.get(path)
        except httpx.HTTPError as exc:
            raise SigNozError(operation, f"transport failure: {exc}") from exc
        if r.status_code >= 400:
            raise SigNozError(operation, r.text[:200], status=r.status_code)
        try:
            return r.json()
        except ValueError:
            return {}

    # ---- reads ----------------------------------------------------------
    def list_services(self, window_seconds: int = 300) -> list[dict[str, Any]]:
        end_ns = _now_ns()
        start_ns = end_ns - window_seconds * 1_000_000_000
        body = self._post(
            "list_services", "/api/v2/services",
            {"start": str(start_ns), "end": str(end_ns)},
        )
        data = body.get("data") if isinstance(body, dict) else body
        return data or []

    def service_p99_ms(self, service: str, window_seconds: int = 30) -> float:
        """Latest p99 latency (ms) for a service, via Query Builder v5 traces."""
        q = build_trace_query(
            f"service.name = '{service}'",
            [{"expression": "p99(duration_nano)"}],
            window_seconds=window_seconds,
            request_type="scalar",
        )
        body = self.query_range(q)
        val = _first_scalar(body)
        return round(val / 1e6, 1) if val is not None else 0.0

    def query_agent_spans(self, service: str = "cafe-agent", window_seconds: int = 300) -> dict[str, float]:
        """Query GenAI / Agent spans from SigNoz via Query Builder v5.

        Extracts agent telemetry attributes like gen_ai.tool.name, gen_ai.usage.*,
        llm.step_count, and llm.cost_usd.
        """
        q = build_trace_query(
            f"service.name = '{service}'",
            [{"expression": "count()"}],
            window_seconds=window_seconds,
            group_by=[
                {"key": "gen_ai.tool.name"},
            ],
            request_type="scalar",
        )
        try:
            body = self.query_range(q)
            return _series_by_group(body)
        except Exception:
            return {}

    def service_p99_series(self, service: str, *, window_seconds: int = 180,
                           step_interval: int = 15) -> list[float]:
        """Chronological p99 latency series (ms) for a service — one query, no sleeps.

        Powers the fast /api/forecast so the chart can draw the *server's* trend.
        """
        q = build_trace_query(
            f"service.name = '{service}'",
            [{"expression": "p99(duration_nano)"}],
            window_seconds=window_seconds, step_interval=step_interval,
            request_type="time_series",
        )
        vals = _series_values(self.query_range(q))
        return [round(v / 1e6, 1) for v in vals]

    def service_error_rate(self, service: str, *, window_seconds: int = 120) -> float:
        """Fraction (0..1) of spans on the service that errored — a second signal."""
        total_q = build_trace_query(f"service.name = '{service}'",
                                    [{"expression": "count()"}],
                                    window_seconds=window_seconds, request_type="scalar")
        err_q = build_trace_query(f"service.name = '{service}' AND has_error = true",
                                  [{"expression": "count()"}],
                                  window_seconds=window_seconds, request_type="scalar")
        total = _first_scalar(self.query_range(total_q)) or 0.0
        errs = _first_scalar(self.query_range(err_q)) or 0.0
        return round(errs / total, 4) if total > 0 else 0.0

    def metric_latest(self, metric_name: str, *, window_seconds: int = 600) -> float | None:
        """Latest value of one of ChronoLens's own gauges, read back from SigNoz."""
        end = _now_ms()
        body = {
            "schemaVersion": "v1", "start": end - window_seconds * 1000, "end": end,
            "requestType": "scalar",
            "compositeQuery": {"queries": [{"type": "builder_query", "spec": {
                "name": "A", "signal": "metrics", "stepInterval": 60,
                "aggregations": [{"metricName": metric_name, "timeAggregation": "latest",
                                  "spaceAggregation": "max"}],
                "groupBy": [],
            }}]},
        }
        try:
            return _first_scalar(self.query_range(body))
        except SigNozError:
            return None

    def agent_turns(self, service: str, *, window_seconds: int = 900,
                    limit: int = 50, span_name: str = "agent.turn") -> list[dict[str, Any]]:
        """Read an AI agent's recent turns **from SigNoz** (GenAI spans).

        Newest-first from the query; returned chronological so drift/loop analysis
        reads them in the order they happened. Fails open to an empty list.
        """
        try:
            body = self.query_range(build_agent_turns_query(
                service, window_seconds=window_seconds, limit=limit, span_name=span_name))
        except Exception:
            return []
        turns = parse_agent_turn_rows(body)
        turns.reverse()  # oldest -> newest
        return turns

    def service_dependency_edges(self, window_seconds: int = 900) -> list[dict[str, Any]]:
        """SigNoz's own service dependency map: [{parent, child, callCount}, ...].

        This is the *real* topology SigNoz derives from traces — the substrate for
        the BLAST-RADIUS forecast. SigNoz has moved this endpoint around between
        versions, so try the known paths and fail open to an empty list (callers
        then fall back to trace-derived topology).
        """
        end_ns = _now_ns()
        start_ns = end_ns - window_seconds * 1_000_000_000
        # SigNoz wants nanosecond epochs as *strings* here (numbers are rejected
        # with "cannot unmarshal number into ... start of type string").
        payload = {"start": str(start_ns), "end": str(end_ns), "tags": []}
        for op, path in (
            ("service_dependency", "/api/v1/dependency_graph"),
            ("service_map", "/api/v1/service/map"),
            ("service_map_v2", "/api/v2/service/map"),
        ):
            try:
                body = self._post(op, path, payload)
            except Exception:
                continue
            data = body.get("data", body) if isinstance(body, dict) else body
            if isinstance(data, list) and data:
                edges: list[dict[str, Any]] = []
                for e in data:
                    if not isinstance(e, dict):
                        continue
                    parent = e.get("parent") or e.get("source") or e.get("from")
                    child = e.get("child") or e.get("target") or e.get("to")
                    if parent and child:
                        edges.append({
                            "parent": str(parent), "child": str(child),
                            "callCount": float(e.get("callCount") or e.get("calls") or 0),
                        })
                if edges:
                    return edges
        return []

    def trace_waterfall(self, trace_id: str) -> list[dict[str, Any]]:
        """Fetch a trace's spans (the waterfall) — evidence for the blast path.

        Tries the known SigNoz trace-detail paths; fails open to an empty list.
        """
        if not trace_id:
            return []
        for op, path in (
            ("trace_detail_v2", f"/api/v2/traces/{trace_id}"),
            ("trace_detail", f"/api/v1/traces/{trace_id}"),
        ):
            try:
                body = self._get(op, path)
            except Exception:
                continue
            data = body.get("data", body) if isinstance(body, dict) else body
            if isinstance(data, list) and data:
                return [s for s in data if isinstance(s, dict)]
            if isinstance(data, dict):
                for key in ("spans", "result", "events"):
                    val = data.get(key)
                    if isinstance(val, list) and val:
                        return [s for s in val if isinstance(s, dict)]
        return []

    def agent_response_bodies(self, service: str, *, window_seconds: int = 900,
                              limit: int = 20) -> list[str]:
        """Recent agent **response texts**, read from SigNoz logs.

        The quality judge needs the whole answer, and span attributes only carry a
        truncated preview — so the agent ships each full response as an OTel log
        record and this reads them back. That makes answer grading telemetry-driven
        instead of re-driving the agent. Fails open to an empty list.
        """
        body = {
            "schemaVersion": "v1",
            "start": _now_ms() - window_seconds * 1000,
            "end": _now_ms(),
            "requestType": "raw",
            "compositeQuery": {"queries": [{
                "type": "builder_query",
                "spec": {
                    "name": "A", "signal": "logs", "disabled": False,
                    "limit": max(1, int(limit)),
                    "filter": {"expression": f"service.name = '{service}'"},
                    "order": [{"key": {"name": "timestamp"}, "direction": "desc"}],
                },
            }]},
        }
        try:
            resp = self.query_range(body)
        except Exception:
            return []
        return _log_bodies(resp, limit=limit)

    def query_range(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("query_range_v5", "/api/v5/query_range", body)

    # ---- writes ---------------------------------------------------------
    def error_log_count(self, service: str, *, severity: str = "ERROR",
                        window_seconds: int = 120) -> float:
        """Count of severity-level logs for a service (CLASSIFY corroboration)."""
        body = self.query_range(build_log_query(service, severity=severity,
                                                window_seconds=window_seconds))
        val = _first_scalar(body)
        return float(val) if val is not None else 0.0

    def span_p99_breakdown(self, service: str, *, window_seconds: int = 300) -> dict[str, float]:
        """p99 latency (ms) per span name for a service — empirical blast path."""
        body = self.query_range(build_span_breakdown_query(service, window_seconds=window_seconds))
        raw = _series_by_group(body)
        return {k: round(v / 1e6, 1) for k, v in raw.items()}

    def dominant_span(self, service: str, **kw) -> str | None:
        """The slowest span name for a service (the data-driven root hop)."""
        breakdown = self.span_p99_breakdown(service, **kw)
        return max(breakdown, key=breakdown.get) if breakdown else None

    def exemplar_trace_id(self, service: str, window_seconds: int = 300) -> str | None:
        """A recent trace id for the service, for a deep-link into SigNoz."""
        q = build_trace_query(
            f"service.name = '{service}'",
            [{"expression": "count()"}],
            window_seconds=window_seconds,
            group_by=[{"name": "trace_id", "fieldContext": "span"}],
            request_type="scalar",
        )
        body = self.query_range(q)
        groups = _series_by_group(body)
        return next(iter(groups), None) if groups else None

    def create_alert_compat(self, rule: dict[str, Any]) -> dict[str, Any]:
        """Create a rule, tolerating SigNoz's two rule endpoints.

        Threshold rules use the v2alpha1 schema and POST to ``/api/v2/rules``.
        **Anomaly rules use the older v1 schema**, which some builds only accept on
        ``/api/v1/rules`` — the v2 endpoint rejects them with ``validation failed``
        and an empty error list. Try v2 first, then fall back to v1 rather than
        making the caller know which vintage a rule is.
        """
        try:
            return self._post("create_alert", "/api/v2/rules", rule)
        except SigNozError:
            return self._post("create_alert_v1", "/api/v1/rules", rule)

    def create_alert(self, rule: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_alert", "/api/v2/rules", rule)

    def create_dashboard(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_dashboard", "/api/v1/dashboards", dashboard)

    def create_saved_view(self, view: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_saved_view", "/api/v1/explorer/views", view)

    def list_rules(self) -> list[dict[str, Any]]:
        body = self._get("list_rules", "/api/v1/rules")
        data = body.get("data") if isinstance(body, dict) else body
        # SigNoz wraps rules as {"data": {"rules": [...]}}.
        if isinstance(data, dict):
            data = data.get("rules", [])
        return data or []

    def alert_fired_count(self, service: str) -> int:
        """How many guard rules for this service are currently in a firing state.

        Best-effort recurrence signal straight from SigNoz's own alert state,
        used to corroborate the ledger in LEARN. Returns 0 if unavailable.
        """
        try:
            rules = self.list_rules()
        except SigNozError:
            return 0
        fired = 0
        for r in rules:
            labels = r.get("labels", {}) if isinstance(r, dict) else {}
            if labels.get("chronolens") == "guard" and labels.get("service") == service:
                state = str(r.get("state", "")).lower()
                if state in ("firing", "alerting"):
                    fired += 1
        return fired

    def create_silence(self, service: str, minutes: int = 5) -> dict[str, Any]:
        """Mute a service's guard alert while the loop remediates (fail-open)."""
        return self._post("create_silence", "/api/v1/silences",
                          build_guard_silence(service, minutes))

    def delete_silence(self, silence_id: str) -> dict[str, Any]:
        try:
            r = self._client.delete(f"/api/v1/silences/{silence_id}")
        except httpx.HTTPError as exc:
            raise SigNozError("delete_silence", f"transport failure: {exc}") from exc
        if r.status_code >= 400:
            raise SigNozError("delete_silence", r.text[:200], status=r.status_code)
        try:
            return r.json()
        except ValueError:
            return {}

    def list_channels(self) -> list[dict[str, Any]]:
        body = self._get("list_channels", "/api/v1/channels")
        return (body.get("data") if isinstance(body, dict) else body) or []

    def channel_webhook_url(self) -> str | None:
        """Discover a notification channel's webhook/Slack URL, so ChronoLens can
        route its own notifications through the same SigNoz channel an alert uses."""
        import json
        for c in self.list_channels():
            raw = c.get("data")
            if not raw:
                continue
            try:
                conf = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                continue
            for key in ("webhook_configs", "slack_configs", "pagerduty_configs"):
                for w in conf.get(key) or []:
                    url = w.get("url") or w.get("api_url")
                    if url:
                        return url
        return None

    def create_webhook_channel(self, name: str, url: str) -> dict[str, Any]:
        return self._post(
            "create_webhook_channel", "/api/v1/channels",
            {"name": name, "webhook_configs": [{"send_resolved": True, "url": url}]},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SigNozClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _first_scalar(body: Any) -> float | None:
    """Pull the first numeric value out of a Query Builder v5 response."""
    if not isinstance(body, dict):
        return None
    data = body.get("data", body)
    # v5 shapes vary: walk common containers looking for a number.
    def _walk(node: Any) -> float | None:
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            return float(node)
        if isinstance(node, dict):
            for key in ("value", "values", "series", "result", "data", "aggregations", "rows"):
                if key in node:
                    v = _walk(node[key])
                    if v is not None:
                        return v
            for v in node.values():
                r = _walk(v)
                if r is not None:
                    return r
        if isinstance(node, list):
            # for [ts, value] pairs prefer the last value
            for item in reversed(node):
                v = _walk(item)
                if v is not None:
                    return v
        return None

    return _walk(data)


def _series_by_group(body: Any) -> dict[str, float]:
    """Extract ``{group_label: value}`` from a grouped Query Builder v5 response.

    The v5 grouped *scalar* shape is::

        data.data.results[].columns = [{name, columnType: "group"|"aggregation"}]
        data.data.results[].data    = [[group_value, agg_value], ...]

    Returns ``{}`` on anything it can't parse, so callers fail open to a static
    fallback.
    """
    out: dict[str, float] = {}
    if not isinstance(body, dict):
        return out
    try:
        results = (((body.get("data") or {}).get("data") or {}).get("results")) or []
        for res in results:
            cols = res.get("columns") or []
            group_idx = next((i for i, c in enumerate(cols)
                              if c.get("columnType") == "group"), None)
            agg_idx = next((i for i, c in enumerate(cols)
                            if c.get("columnType") == "aggregation"), None)
            if group_idx is None or agg_idx is None:
                continue
            for row in res.get("data") or []:
                if isinstance(row, list) and len(row) > max(group_idx, agg_idx):
                    label, val = row[group_idx], row[agg_idx]
                    if isinstance(label, str) and isinstance(val, (int, float)) \
                            and not isinstance(val, bool):
                        out[label] = float(val)
    except Exception:
        return {}
    return out


def _series_values(body: Any) -> list[float]:
    """Extract a chronological list of numeric values from a v5 time_series body.

    Shape: data.data.results[].aggregations[].series[].values[] = [{timestamp, value}].
    Sorted by timestamp ascending. Returns [] on anything unparseable.
    """
    if not isinstance(body, dict):
        return []
    pairs: list[tuple[float, float]] = []
    try:
        results = (((body.get("data") or {}).get("data") or {}).get("results")) or []
        for res in results:
            aggs = res.get("aggregations") or []
            containers = []
            for a in aggs:
                containers.extend(a.get("series") or [])
            containers.extend(res.get("series") or [])
            for s in containers:
                for v in s.get("values") or []:
                    if isinstance(v, dict) and v.get("value") is not None:
                        try:
                            pairs.append((float(v.get("timestamp", 0)), float(v["value"])))
                        except (TypeError, ValueError):
                            pass
                    elif isinstance(v, list) and len(v) >= 2:
                        try:
                            pairs.append((float(v[0]), float(v[1])))
                        except (TypeError, ValueError):
                            pass
    except Exception:
        return []
    pairs.sort(key=lambda p: p[0])
    return [v for _, v in pairs]


def _log_bodies(resp: dict[str, Any], *, limit: int = 20) -> list[str]:
    """Pull log message bodies out of a v5 ``requestType:"raw"`` logs response.

    The v5 raw shape nests rows under ``data.results[].rows[].data``, and the message
    lives under ``body`` (with ``gen_ai.response.text`` as a richer attribute when the
    producer sets it). Shapes vary between SigNoz builds, so this walks defensively
    and returns whatever readable strings it finds.
    """
    out: list[str] = []

    def take(row: Any) -> None:
        if len(out) >= limit or not isinstance(row, dict):
            return
        data = row.get("data") if isinstance(row.get("data"), dict) else row
        if not isinstance(data, dict):
            return
        # prefer the explicit full-text attribute, then the log body
        for key in ("gen_ai.response.text", "body", "message"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
                return
        attrs = data.get("attributes") or data.get("attributes_string")
        if isinstance(attrs, dict):
            val = attrs.get("gen_ai.response.text")
            if isinstance(val, str) and val.strip():
                out.append(val.strip())

    def walk(node: Any) -> None:
        if len(out) >= limit:
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            rows = node.get("rows")
            if isinstance(rows, list):
                for r in rows:
                    take(r)
                return
            for value in node.values():
                walk(value)

    walk(resp.get("data", resp))
    return out[:limit]
