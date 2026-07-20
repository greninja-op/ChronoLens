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
    return {
        "title": f"ChronoLens guard - {service}",
        "description": (
            f"Auto-created by ChronoLens after preventing a breach on {service}. "
            f"Keeps the prevented incident watched."
        ),
        "tags": ["chronolens", "guard", service],
        "widgets": [panel, impact_panel],
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

    def create_alert(self, rule: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_alert", "/api/v2/rules", rule)

    def create_dashboard(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_dashboard", "/api/v1/dashboards", dashboard)

    def create_saved_view(self, view: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_saved_view", "/api/v1/explorer/views", view)

    def list_rules(self) -> list[dict[str, Any]]:
        body = self._get("list_rules", "/api/v1/rules")
        data = body.get("data") if isinstance(body, dict) else body
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
