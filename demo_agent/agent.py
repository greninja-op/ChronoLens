"""ChronoLens demo AI agent — a café assistant we can watch, drift, and break.

Unlike the demo *store* (a web service), this is an LLM agent instrumented with
OpenTelemetry GenAI-style span attributes, so ChronoLens can observe **behavior**
(which tools, how many steps, tokens, cost, model) — not just latency.

It runs in three modes so the three agent features are demoable:

    normal  — 2-step turns, gpt-4o-mini, short answers  (the learned baseline)
    drift   — model swapped to gpt-4o, a new `web_search` tool appears,
              answers get long  (a silent behavior change; no error, normal latency)
    loop    — the agent spirals: it calls the same tool over and over, tokens and
              cost climb, and it never converges  (runaway / cost spiral)

Each /chat emits one parent `agent.turn` span with child `gen_ai.chat` and
`tool.execute` spans carrying the attributes the analyzers read.
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
from opentelemetry.trace import SpanKind

SERVICE_NAME = os.getenv("AGENT_SERVICE_NAME", "chronolens-agent")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "localhost:4317")

# rough per-1k-token prices (USD) so the loop's cost spiral is a real number
PRICE = {"gpt-4o-mini": (0.00015, 0.0006), "gpt-4o": (0.005, 0.015)}

_state = {"mode": "normal"}

# what a turn looks like in each mode: (model, tools, in_tok, out_tok, steps)
BASELINE_TOOLS = ["get_menu", "place_order"]


def _init_tracer() -> trace.Tracer:
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("chronolens.agent")


tracer = _init_tracer()
app = FastAPI(title="ChronoLens Demo Agent (café assistant)")


def _cost(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICE.get(model, PRICE["gpt-4o-mini"])
    return round(pin * tin / 1000 + pout * tout / 1000, 5)


def _plan(mode: str) -> dict:
    """Decide the shape of this turn based on the current mode."""
    if mode == "drift":
        # model swapped, a NEW tool appears, answers get long — all silent
        return {"model": "gpt-4o",
                "tools": ["web_search", "get_menu", "place_order"],
                "in_tok": random.randint(300, 380), "out_tok": random.randint(430, 560)}
    if mode == "loop":
        # spiral: the same tool over and over, never converging
        n = random.randint(9, 16)
        return {"model": "gpt-4o-mini", "tools": ["get_menu"] * n,
                "in_tok": 90 * n, "out_tok": 60 * n, "looping": True}
    # normal / baseline
    return {"model": "gpt-4o-mini", "tools": list(BASELINE_TOOLS),
            "in_tok": random.randint(90, 140), "out_tok": random.randint(110, 190)}


@app.get("/chat")
def chat(msg: str = "a latte and a croissant please") -> dict:
    now = time.time()
    plan = _plan(_state["mode"])
    model, tools = plan["model"], plan["tools"]
    tin, tout = plan["in_tok"], plan["out_tok"]
    steps = len(tools)
    cost = _cost(model, tin, tout)

    with tracer.start_as_current_span("agent.turn", kind=SpanKind.SERVER) as turn:
        turn.set_attribute("gen_ai.system", "openai")
        turn.set_attribute("gen_ai.request.model", model)
        turn.set_attribute("gen_ai.usage.input_tokens", tin)
        turn.set_attribute("gen_ai.usage.output_tokens", tout)
        turn.set_attribute("llm.step_count", steps)
        turn.set_attribute("llm.cost_usd", cost)
        turn.set_attribute("agent.tools", ",".join(tools))
        turn.set_attribute("agent.looping", bool(plan.get("looping")))
        turn.set_attribute("agent.answer_len", tout)
        # one LLM "thinking" span
        with tracer.start_as_current_span("gen_ai.chat", kind=SpanKind.INTERNAL) as llm:
            llm.set_attribute("gen_ai.request.model", model)
            llm.set_attribute("gen_ai.usage.input_tokens", tin)
            llm.set_attribute("gen_ai.usage.output_tokens", tout)
            time.sleep(0.02)
        # one span per tool call (this is what reveals loops / new tools)
        for t in tools:
            with tracer.start_as_current_span("tool.execute", kind=SpanKind.INTERNAL) as ts:
                ts.set_attribute("tool.name", t)
                time.sleep(0.005)

    return {"mode": _state["mode"], "model": model, "tools": tools, "steps": steps,
            "input_tokens": tin, "output_tokens": tout, "cost_usd": cost,
            "looping": bool(plan.get("looping"))}


@app.get("/admin/mode")
def set_mode(mode: str = "normal") -> dict:
    if mode not in ("normal", "drift", "loop"):
        return {"error": f"unknown mode '{mode}' (use normal|drift|loop)"}
    _state["mode"] = mode
    return {"mode": mode}


@app.get("/admin/status")
def status() -> dict:
    return {"mode": _state["mode"], "service": SERVICE_NAME,
            "baseline": {"model": "gpt-4o-mini", "tools": BASELINE_TOOLS,
                         "typical_steps": 2, "typical_out_tokens": 150}}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME}


if __name__ == "__main__":
    import uvicorn

    print(f"ChronoLens demo agent -> service '{SERVICE_NAME}' -> OTLP {OTLP_ENDPOINT}")
    print("Control: http://localhost:8091/admin/status  ·  chat: /chat  ·  mode: /admin/mode?mode=drift|loop")
    uvicorn.run(app, host="0.0.0.0", port=8091, log_level="warning")
