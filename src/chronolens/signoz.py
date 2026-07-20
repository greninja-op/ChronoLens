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
            "queryType": "builder",
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

    def service_p99_ms(self, service: str, window_seconds: int = 120) -> float:
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
    def create_alert(self, rule: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_alert", "/api/v2/rules", rule)

    def create_dashboard(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        return self._post("create_dashboard", "/api/v1/dashboards", dashboard)

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
