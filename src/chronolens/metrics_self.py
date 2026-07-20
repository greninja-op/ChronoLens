"""ChronoLens emits its own metrics to SigNoz.

Beyond self-tracing, the loop publishes a few gauges so its impact is visible on
a SigNoz dashboard, not just in the ledger:

    chronolens.prevented_total     incidents prevented so far
    chronolens.seconds_to_breach   lead time on the latest forecast
    chronolens.cost_saved_usd      dollars returned on cooldown (latest)
    chronolens.capacity_units      current capacity the target is running at

Emission always fails open — a broken metrics exporter must never break the
reliability agent it's measuring.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("chronolens.metrics_self")

SERVICE_NAME = os.getenv("CHRONOLENS_SERVICE_NAME", "chronolens")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "localhost:4317")

_meter = None
_gauges: dict = {}
_last: dict[str, float] = {}


def _enabled() -> bool:
    return os.getenv("CHRONOLENS_SELF_OTEL", "on").lower() not in ("off", "0", "false", "no")


def _init() -> None:
    global _meter, _gauges
    if _meter is not None or not _enabled():
        return
    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True),
            export_interval_millis=10_000,
        )
        provider = MeterProvider(
            resource=Resource.create({"service.name": SERVICE_NAME}),
            metric_readers=[reader],
        )
        metrics.set_meter_provider(provider)
        _meter = metrics.get_meter("chronolens.self")

        def _obs(name):
            def cb(_options):
                from opentelemetry.metrics import Observation

                return [Observation(_last.get(name, 0.0))]

            return cb

        for name, unit, desc in (
            ("chronolens.prevented_total", "1", "incidents prevented"),
            ("chronolens.seconds_to_breach", "s", "lead time on latest forecast"),
            ("chronolens.cost_saved_usd", "usd", "dollars returned on cooldown"),
            ("chronolens.capacity_units", "1", "current target capacity"),
        ):
            _gauges[name] = _meter.create_observable_gauge(
                name, callbacks=[_obs(name)], unit=unit, description=desc
            )
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to init ChronoLens self-metrics")


def record_metrics(*, prevented_total: float | None = None,
                   seconds_to_breach: float | None = None,
                   cost_saved_usd: float | None = None,
                   capacity_units: float | None = None) -> None:
    """Update the latest gauge values. Safe to call from the loop; never raises."""
    if not _enabled():
        return
    try:
        _init()
        if prevented_total is not None:
            _last["chronolens.prevented_total"] = float(prevented_total)
        if seconds_to_breach is not None:
            _last["chronolens.seconds_to_breach"] = float(seconds_to_breach)
        if cost_saved_usd is not None:
            _last["chronolens.cost_saved_usd"] = float(cost_saved_usd)
        if capacity_units is not None:
            _last["chronolens.capacity_units"] = float(capacity_units)
    except Exception:
        logger.exception("failed to record ChronoLens self-metrics")


def flush(timeout_millis: int = 5000) -> None:
    """Force-export buffered metrics (short-lived CLI safety)."""
    try:
        from opentelemetry import metrics

        provider = metrics.get_meter_provider()
        force = getattr(provider, "force_flush", None)
        if callable(force):
            force(timeout_millis)
    except Exception:
        logger.exception("failed to flush ChronoLens self-metrics")
