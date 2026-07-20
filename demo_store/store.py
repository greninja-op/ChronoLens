"""ChronoLens demo store — the app we watch, predict on, and rescue.

A small OpenTelemetry-instrumented "online store". Each request fans out into
cart -> inventory -> payment -> db spans, so SigNoz sees a real service graph.

The point of this app is a *predictable, preventable* failure:

    demand(t) rises over time (the "traffic ramp" fault). Latency stays flat
    while demand <= capacity, then climbs sharply once demand overtakes capacity
    and eventually breaches the SLO.

ChronoLens forecasts that crossover and pulls a **reversible lever** — scaling
capacity — *before* the breach. Scale up in time and the latency never reaches
the wall. That's an honest, demonstrable "prevent".

Admin API:
    GET  /admin/fault?mode=traffic-ramp&level=30   -> start a gradual load ramp
    GET  /admin/fault?mode=off                     -> clear the fault
    GET  /admin/status                             -> live model state + est. p99
    POST /admin/lever?action=scale&value=2         -> reversible fix (scale out)
    POST /admin/lever?action=restart               -> rolling restart (clears ramp)
    POST /admin/lever?action=reset                 -> capacity + fault back to default
"""
from __future__ import annotations

import os
import random
import time

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

SERVICE_NAME = os.getenv("STORE_SERVICE_NAME", "chronolens-store")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "localhost:4317")

# --- latency model constants -------------------------------------------------
BASE_MS = 42.0            # healthy baseline latency
DEFAULT_CAPACITY = 2.0    # "worker units" of serving capacity
BASE_DEMAND = 1.0         # steady-state demand (well under default capacity)
PENALTY_MS = 900.0        # latency added per unit of overload (demand - capacity)

# --- live model state --------------------------------------------------------
_state = {
    "capacity": DEFAULT_CAPACITY,
    "fault_mode": "off",
    "fault_level": 0.0,
    "fault_start": 0.0,
}


def _demand(now: float) -> float:
    """Current demand on the service. The traffic ramp grows it gradually."""
    if _state["fault_mode"] == "traffic-ramp":
        elapsed = max(0.0, now - _state["fault_start"])
        # level/1000 units per second -> level=30 crosses the default capacity
        # (~33s) and breaches the 500ms SLO (~50s): gradual enough to forecast.
        return BASE_DEMAND + (_state["fault_level"] / 1000.0) * elapsed
    return BASE_DEMAND


def _latency_ms(now: float) -> float:
    """Model latency from how far demand exceeds capacity."""
    overload = max(0.0, _demand(now) - _state["capacity"])
    return BASE_MS + overload * PENALTY_MS + random.uniform(0.0, 8.0)


# --- OpenTelemetry setup -----------------------------------------------------
def _init_tracer() -> trace.Tracer:
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("chronolens.store")


tracer = _init_tracer()
app = FastAPI(title="ChronoLens Demo Store")


def _child(name: str, ms: float) -> None:
    """Emit a downstream child span that takes ``ms`` milliseconds."""
    with tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as span:
        span.set_attribute("component", name)
        time.sleep(max(0.0, ms) / 1000.0)


@app.get("/order")
def order() -> dict:
    """Place an order: cart -> inventory -> payment -> db. Latency tracks the model."""
    now = time.time()
    total = _latency_ms(now)
    # split the request's latency across the downstream hops
    with tracer.start_as_current_span("/order", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", "GET")
        span.set_attribute("http.route", "/order")
        span.set_attribute("store.capacity", _state["capacity"])
        span.set_attribute("store.demand", round(_demand(now), 3))
        _child("cart.lookup", total * 0.15)
        _child("inventory.check", total * 0.20)
        with tracer.start_as_current_span("payment.charge", kind=SpanKind.INTERNAL):
            _child("payment.db_query", total * 0.45)
        _child("order.db_write", total * 0.20)
        breaching = total >= 500.0
        if breaching:
            span.set_status(Status(StatusCode.ERROR, "latency SLO breach"))
        return {"ok": not breaching, "latency_ms": round(total, 1)}


@app.get("/admin/fault")
def set_fault(mode: str = "off", level: float = 0.0) -> dict:
    """Set the fault mode. 'traffic-ramp' gradually raises demand over time."""
    _state["fault_mode"] = mode
    _state["fault_level"] = float(level)
    _state["fault_start"] = time.time()
    return {"fault_mode": mode, "level": level}


@app.get("/admin/status")
def status() -> dict:
    now = time.time()
    return {
        "capacity": round(_state["capacity"], 2),
        "demand": round(_demand(now), 3),
        "fault_mode": _state["fault_mode"],
        "fault_level": _state["fault_level"],
        "est_latency_ms": round(_latency_ms(now), 1),
    }


@app.post("/admin/lever")
def lever(action: str, value: float = 2.0) -> dict:
    """Apply a reversible remediation lever. Returns a rollback description."""
    if action == "scale":
        _state["capacity"] += value
        return {
            "action": "scale",
            "value": value,
            "capacity": _state["capacity"],
            "rollback": f"scale by {-value} (capacity back to {_state['capacity'] - value})",
        }
    if action == "restart":
        # rolling restart clears the accumulated ramp (fresh instance)
        _state["fault_start"] = time.time()
        return {"action": "restart", "capacity": _state["capacity"], "rollback": "none (idempotent)"}
    if action == "reset":
        _state["capacity"] = DEFAULT_CAPACITY
        _state["fault_mode"] = "off"
        _state["fault_level"] = 0.0
        return {"action": "reset", "capacity": _state["capacity"], "rollback": "none"}
    return {"error": f"unknown action '{action}'"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


if __name__ == "__main__":
    import uvicorn

    print(f"ChronoLens demo store -> service '{SERVICE_NAME}' -> OTLP {OTLP_ENDPOINT}")
    print("Control: http://localhost:8090/admin/status")
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="warning")
