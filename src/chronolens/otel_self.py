"""ChronoLens instruments its own loop, so it shows up in SigNoz too.

Every stage (foresee / prevent / verify / record) emits one span, linked under
a single loop trace via a shared root. Emission always fails open — a broken
exporter must never crash the reliability agent.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

logger = logging.getLogger("chronolens.otel_self")

SERVICE_NAME = os.getenv("CHRONOLENS_SERVICE_NAME", "chronolens")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "localhost:4317")

_STAGE = "chronolens.stage"
_OUTCOME = "chronolens.outcome"
_LOOP = "chronolens.loop_id"

_loop_contexts: "dict[str, Context]" = {}


def _init_provider() -> None:
    if os.getenv("CHRONOLENS_SELF_OTEL", "on").lower() in ("off", "0", "false", "no"):
        return
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
        )
        trace.set_tracer_provider(provider)
    except Exception:  # pragma: no cover - defensive
        logger.exception("failed to init ChronoLens self-observability")


_init_provider()


def _tracer():
    return trace.get_tracer("chronolens.self")


def _loop_context(loop_id: str) -> "Context | None":
    ctx = _loop_contexts.get(loop_id)
    if ctx is not None:
        return ctx
    try:
        root = _tracer().start_span("chronolens.loop", kind=SpanKind.INTERNAL)
        root.set_attribute(_LOOP, loop_id)
        ctx = trace.set_span_in_context(root)
        root.end()
    except Exception:
        logger.exception("failed to open ChronoLens loop trace")
        return None
    if len(_loop_contexts) > 256:
        _loop_contexts.pop(next(iter(_loop_contexts)), None)
    _loop_contexts[loop_id] = ctx
    return ctx


@contextmanager
def stage_span(stage: str, loop_id: str) -> Iterator[Span]:
    """Emit one self-observability span for a ChronoLens ``stage``."""
    span: Span = trace.INVALID_SPAN
    try:
        span = _tracer().start_span(
            "chronolens." + stage, context=_loop_context(loop_id), kind=SpanKind.INTERNAL
        )
        span.set_attribute(_STAGE, stage)
        span.set_attribute(_LOOP, loop_id)
    except Exception:
        logger.exception("failed to start ChronoLens stage span for %s", stage)
        span = trace.INVALID_SPAN

    body_exc: "BaseException | None" = None
    try:
        yield span
    except Exception as exc:
        body_exc = exc
    try:
        span.set_attribute(_OUTCOME, "error" if body_exc else "ok")
        if body_exc:
            span.set_status(Status(StatusCode.ERROR, str(body_exc)))
            span.record_exception(body_exc)
        span.end()
    except Exception:
        logger.exception("failed to emit ChronoLens stage span for %s", stage)
    if body_exc is not None:
        raise body_exc


def flush(timeout_millis: int = 5000) -> None:
    """Force-export buffered spans (short-lived CLI safety)."""
    try:
        provider = trace.get_tracer_provider()
        force = getattr(provider, "force_flush", None)
        if callable(force):
            force(timeout_millis)
    except Exception:
        logger.exception("failed to flush ChronoLens self-observability spans")
