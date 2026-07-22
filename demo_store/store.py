"""ChronoLens demo store — the app we watch, predict on, and rescue.

A small OpenTelemetry-instrumented "online store". Each request fans out into
cart -> inventory -> payment -> db spans, so SigNoz sees a real service graph.

It can be broken in several *distinct, gradual, preventable* ways, each of which
maps to a different reversible remediation (the ChronoLens playbook):

    fault                signal ChronoLens sees     reversible fix (lever)
    -------------------  ------------------------    -----------------------
    traffic-ramp/-wave   broad latency (load)        scale out  / scale in
    dependency-slow      one hop (payment.db) slow   circuit-break the dep
    pool-leak            saturation → latency+errors pool-resize
    error-spike          error rate jumps (bad deploy) rollback
    memory-leak          slow creep → latency        rolling restart

Each fault ramps gradually so ChronoLens can forecast it; each lever is
reversible so acting is safe.
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

# --- model constants ---------------------------------------------------------
BASE_MS = 42.0
DEFAULT_CAPACITY = 2.0
DEFAULT_POOL = 2.0
BASE_DEMAND = 1.0
PENALTY_MS = 900.0        # latency per unit of load overload
DEP_PENALTY_MS = 1400.0   # latency per unit of dependency severity
POOL_PENALTY_MS = 1100.0  # latency per unit of pool overload
MEM_PENALTY_MS = 700.0    # latency per unit of memory pressure
WAVE_PEAK_S = 45.0

# --- live model state --------------------------------------------------------
_state = {
    "capacity": DEFAULT_CAPACITY,
    "pool_size": DEFAULT_POOL,
    "fault_mode": "off",
    "fault_level": 0.0,
    "fault_start": 0.0,
    # reversible mitigations
    "circuit_open": False,   # isolates a slow dependency
    "rolled_back": False,    # clears a bad-deploy error spike
    "restarted_at": 0.0,     # resets the memory-leak clock
}


def _elapsed(now: float) -> float:
    return max(0.0, now - _state["fault_start"])


def _demand(now: float) -> float:
    mode, rate, el = _state["fault_mode"], _state["fault_level"] / 1000.0, _elapsed(now)
    if mode == "traffic-ramp":
        return BASE_DEMAND + rate * el
    if mode == "traffic-wave":
        if el <= WAVE_PEAK_S:
            return BASE_DEMAND + rate * el
        return BASE_DEMAND + max(0.0, rate * WAVE_PEAK_S - rate * (el - WAVE_PEAK_S))
    return BASE_DEMAND


def _severities(now: float) -> dict:
    """Per-fault severity contributions (each ramps gradually)."""
    mode, rate, el = _state["fault_mode"], _state["fault_level"] / 1000.0, _elapsed(now)
    sev = {"load": 0.0, "dependency": 0.0, "pool": 0.0, "memory": 0.0, "errors": 0.0}
    # load
    sev["load"] = max(0.0, _demand(now) - _state["capacity"])
    # dependency (mitigated by circuit breaker)
    if mode == "dependency-slow" and not _state["circuit_open"]:
        sev["dependency"] = rate * el
    # pool saturation (mitigated by pool-resize)
    if mode == "pool-leak":
        pool_demand = BASE_DEMAND + rate * el
        sev["pool"] = max(0.0, pool_demand - _state["pool_size"])
    # memory creep (mitigated by restart -> resets clock)
    if mode == "memory-leak":
        since = max(0.0, now - max(_state["fault_start"], _state["restarted_at"]))
        sev["memory"] = rate * since
    # error spike / bad deploy (mitigated by rollback)
    if mode == "error-spike" and not _state["rolled_back"]:
        sev["errors"] = min(1.0, 0.1 + rate * el)  # fraction of requests failing
    return sev


def _latency_ms(now: float) -> float:
    s = _severities(now)
    return (BASE_MS + s["load"] * PENALTY_MS + s["dependency"] * DEP_PENALTY_MS
            + s["pool"] * POOL_PENALTY_MS + s["memory"] * MEM_PENALTY_MS
            + random.uniform(0.0, 8.0))


def _error_rate(now: float) -> float:
    s = _severities(now)
    # pool overflow and memory pressure also shed errors past a point
    return min(1.0, s["errors"] + max(0.0, s["pool"] - 0.5) * 0.3 + max(0.0, s["memory"] - 0.8) * 0.2)


def _dominant_signal(now: float) -> str:
    s = _severities(now)
    weighted = {
        "load": s["load"] * PENALTY_MS,
        "dependency": s["dependency"] * DEP_PENALTY_MS,
        "pool": s["pool"] * POOL_PENALTY_MS,
        "memory": s["memory"] * MEM_PENALTY_MS,
        "errors": s["errors"] * 1000.0,
    }
    top = max(weighted, key=weighted.get)
    return top if weighted[top] > 1.0 else "healthy"


# --- OpenTelemetry setup -----------------------------------------------------
def _init_tracer() -> trace.Tracer:
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("chronolens.store")


tracer = _init_tracer()
app = FastAPI(title="ChronoLens Demo Store")


def _child(name: str, ms: float, err: bool = False) -> None:
    with tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as span:
        span.set_attribute("component", name)
        time.sleep(max(0.0, ms) / 1000.0)
        if err:
            span.set_status(Status(StatusCode.ERROR, "downstream error"))


@app.get("/order")
def order() -> dict:
    now = time.time()
    total = _latency_ms(now)
    sev = _severities(now)
    failing = random.random() < _error_rate(now)
    with tracer.start_as_current_span("/order", kind=SpanKind.SERVER) as span:
        span.set_attribute("http.method", "GET")
        span.set_attribute("http.route", "/order")
        span.set_attribute("store.capacity", _state["capacity"])
        span.set_attribute("store.dominant_signal", _dominant_signal(now))
        _child("cart.lookup", total * 0.15)
        _child("inventory.check", total * 0.15)
        with tracer.start_as_current_span("payment.charge", kind=SpanKind.INTERNAL):
            # the dependency fault concentrates in payment.db_query
            dep_extra = sev["dependency"] * DEP_PENALTY_MS
            _child("payment.db_query", total * 0.35 + dep_extra)
        _child("order.db_write", total * 0.20, err=failing)
        if failing or total >= 500.0:
            span.set_status(Status(StatusCode.ERROR, "breach/error (injected)"))
        return {"ok": not (failing or total >= 500.0), "latency_ms": round(total, 1)}


@app.get("/admin/fault")
def set_fault(mode: str = "off", level: float = 0.0) -> dict:
    _state["fault_mode"] = mode
    _state["fault_level"] = float(level)
    _state["fault_start"] = time.time()
    # a fresh fault clears stale mitigations so it can actually manifest
    _state["circuit_open"] = False
    _state["rolled_back"] = False
    _state["restarted_at"] = 0.0
    return {"fault_mode": mode, "level": level}


@app.get("/admin/status")
def status() -> dict:
    now = time.time()
    return {
        "capacity": round(_state["capacity"], 2),
        "baseline_capacity": DEFAULT_CAPACITY,
        "pool_size": round(_state["pool_size"], 2),
        "demand": round(_demand(now), 3),
        "headroom": round(_state["capacity"] - _demand(now), 3),
        "fault_mode": _state["fault_mode"],
        "fault_level": _state["fault_level"],
        "dominant_signal": _dominant_signal(now),
        "est_latency_ms": round(_latency_ms(now), 1),
        "est_error_pct": round(_error_rate(now) * 100, 1),
        "circuit_open": _state["circuit_open"],
        "rolled_back": _state["rolled_back"],
    }


@app.post("/admin/lever")
def lever(action: str, value: float = 2.0) -> dict:
    """Apply a reversible remediation lever. Returns a rollback description."""
    a = action
    if a == "scale":
        _state["capacity"] += value
        return {"action": a, "value": value, "capacity": _state["capacity"],
                "rollback": f"scale by {-value}"}
    if a == "circuit-break":
        _state["circuit_open"] = True
        return {"action": a, "rollback": "close the circuit breaker"}
    if a == "close-circuit":
        _state["circuit_open"] = False
        return {"action": a, "rollback": "re-open the circuit breaker"}
    if a == "redeploy":
        _state["rolled_back"] = False
        return {"action": a, "rollback": "roll back again"}
    if a == "pool-resize":
        _state["pool_size"] += value
        return {"action": a, "value": value, "pool_size": _state["pool_size"],
                "rollback": f"resize pool by {-value}"}
    if a == "restart":
        _state["restarted_at"] = time.time()
        return {"action": a, "rollback": "none (idempotent rolling restart)"}
    if a == "rollback":
        _state["rolled_back"] = True
        return {"action": a, "rollback": "re-deploy the new version"}
    if a == "reset":
        _state.update(capacity=DEFAULT_CAPACITY, pool_size=DEFAULT_POOL,
                      fault_mode="off", fault_level=0.0, circuit_open=False,
                      rolled_back=False, restarted_at=0.0)
        return {"action": a, "rollback": "none"}
    return {"error": f"unknown action '{a}'"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


if __name__ == "__main__":
    import uvicorn

    print(f"ChronoLens demo store -> service '{SERVICE_NAME}' -> OTLP {OTLP_ENDPOINT}")
    print("Control: http://localhost:8090/admin/status")
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="warning")
