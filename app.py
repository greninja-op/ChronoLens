"""ChronoLens Mission Control — web UI + API.

Run (from the chronolens/ folder, with the demo store already running on :8090):
    set PYTHONPATH=src        (Windows)   /   export PYTHONPATH=src   (bash)
    python app.py
Then open http://localhost:8095
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from chronolens.config import Config  # noqa: E402
from chronolens.loop import run_loop  # noqa: E402
from chronolens.record import Ledger  # noqa: E402
from chronolens.signoz import SigNozClient  # noqa: E402

HERE = os.path.dirname(__file__)
cfg = Config.load()

WARN_FRAC = 0.8  # p99 within 80% of SLO -> "warning"


def health_state(p99_ms: float, slo_ms: float) -> str:
    if slo_ms <= 0 or p99_ms >= slo_ms:
        return "critical"
    if p99_ms >= WARN_FRAC * slo_ms:
        return "warning"
    return "healthy"


app = FastAPI(title="ChronoLens Mission Control")


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/respond/stream")
def respond_stream(managed: bool = True):
    """Server-Sent Events: stream each loop stage as it happens, so the UI's
    circuit lights up LEARN→…→RECORD live instead of all-at-once at the end."""
    q: "queue.Queue" = queue.Queue()

    def worker():
        try:
            with SigNozClient(cfg) as sn:
                res = run_loop(sn, cfg, managed=managed, emit=lambda ev: q.put(ev))
            q.put({"_done": True, "outcome": res.get("outcome")})
        except Exception as e:
            q.put({"_done": True, "error": str(e)})

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            yield f"data: {json.dumps(ev)}\n\n"
            if ev.get("_done"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/services")
def services():
    try:
        with SigNozClient(cfg) as sn:
            data = sn.list_services(window_seconds=300)
        out = []
        for s in data:
            name = s.get("serviceName")
            if name == "chronolens":
                continue  # hide our own self-trace service from the health grid
            calls = float(s.get("numCalls", 0) or 0)
            errs = float(s.get("numErrors", 0) or 0)
            p99_ms = round(float(s.get("p99", 0) or 0) / 1e6, 1)
            out.append({
                "name": name,
                "p99_ms": p99_ms,
                "error_pct": round((errs / calls * 100) if calls else 0.0, 1),
                "calls": int(calls),
                "slo_ms": cfg.p99_slo_ms,
                "state": health_state(p99_ms, cfg.p99_slo_ms),
            })
        out.sort(key=lambda x: x["p99_ms"], reverse=True)
        return {"services": out}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/fault")
def fault(mode: str = "off", level: float = 0.0):
    try:
        r = httpx.get(f"{cfg.demo_store_url}/admin/fault",
                      params={"mode": mode, "level": level}, timeout=8)
        return r.json()
    except Exception as e:
        return JSONResponse({"error": f"demo store not reachable: {e}"}, status_code=502)


@app.get("/api/store")
def store_status():
    try:
        return httpx.get(f"{cfg.demo_store_url}/admin/status", timeout=8).json()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ---- agent observability (drift / loop / quality) -----------------------
import os as _os

_AGENT_SERVICE = _os.getenv("AGENT_SERVICE_NAME", "chronolens-agent")


@app.get("/api/agent/status")
def agent_status():
    try:
        return httpx.get(f"{cfg.agent_url}/admin/status", timeout=6).json()
    except Exception as e:
        return JSONResponse({"error": f"agent not reachable: {e}"}, status_code=502)


@app.post("/api/agent/mode")
def agent_mode(mode: str = "normal"):
    try:
        return httpx.get(f"{cfg.agent_url}/admin/mode", params={"mode": mode}, timeout=6).json()
    except Exception as e:
        return JSONResponse({"error": f"agent not reachable: {e}"}, status_code=502)


@app.get("/api/agent/loopcheck")
def agent_loopcheck():
    """Drive one agent turn and run the loop guard on it (the cost-spiral breaker),
    corroborating with live SigNoz agent spans via Query Builder v5."""
    from chronolens.loopguard import evaluate
    try:
        turn = httpx.get(f"{cfg.agent_url}/chat", timeout=12).json()
    except Exception as e:
        return JSONResponse({"error": f"agent not reachable: {e}"}, status_code=502)

    # Corroborate with live SigNoz GenAI spans (full-circle agent observability)
    try:
        with SigNozClient(cfg) as sn:
            spans = sn.query_agent_spans(_AGENT_SERVICE, window_seconds=120)
            if spans:
                turn["signoz_telemetry"] = spans
    except Exception:
        pass

    v = evaluate(turn.get("steps", 0), turn.get("tools", []), turn.get("cost_usd", 0.0),
                 max_steps=cfg.agent_max_steps, cost_budget=cfg.agent_cost_budget_usd,
                 repeat_threshold=cfg.agent_repeat_threshold)
    slack_posted = False
    if v.looping and cfg.slack_enabled():
        kind = "cost" if v.cost_usd > cfg.agent_cost_budget_usd else "loop"
        detail = (f"*Detected:* {v.reason}\n"
                  f"*Cost so far:* ${v.cost_usd} · breaking at step {v.break_at_step} "
                  f"saves ~${v.saved_usd}")
        try:
            from chronolens.slack_bot import post_agent_approval
            slack_posted = post_agent_approval(
                cfg, kind=kind, service=_AGENT_SERVICE, detail=detail).ok
        except Exception:
            slack_posted = False
    return {"turn": turn, "verdict": v.__dict__, "slack_posted": slack_posted}


def _drive_agent(n: int) -> list[dict]:
    turns = []
    with httpx.Client(timeout=12) as c:
        for _ in range(max(1, n)):
            try:
                turns.append(c.get(f"{cfg.agent_url}/chat").json())
            except Exception:
                break
    return turns


@app.post("/api/agent/baseline")
def agent_baseline(samples: int = 10):
    """Capture the agent's current behavior as the drift baseline (run in normal mode)."""
    from chronolens.drift import fingerprint, save_baseline
    turns = _drive_agent(samples)
    if not turns:
        return JSONResponse({"error": "agent not reachable"}, status_code=502)
    fp = fingerprint(turns)
    save_baseline(fp, Ledger().root)
    return {"captured": fp.__dict__}


@app.get("/api/agent/drift")
def agent_drift(samples: int = 10):
    """Compare recent agent behavior to the saved baseline and score the drift."""
    from chronolens.drift import drift_score, fingerprint, load_baseline
    base = load_baseline(Ledger().root)
    if base is None:
        return {"error": "no baseline yet — capture one first (POST /api/agent/baseline)"}
    turns = _drive_agent(samples)
    if not turns:
        return JSONResponse({"error": "agent not reachable"}, status_code=502)
    recent = fingerprint(turns)
    d = drift_score(base, recent, threshold=cfg.drift_threshold)
    slack_posted = False
    if d.drifted and cfg.slack_enabled():
        detail = (f"*Drift score:* {d.score} (threshold {cfg.drift_threshold})\n"
                  f"*Changes:* " + ("; ".join(d.changes) if d.changes else "behavior shifted"))
        try:
            from chronolens.slack_bot import post_agent_approval
            slack_posted = post_agent_approval(
                cfg, kind="drift", service=_AGENT_SERVICE, detail=detail).ok
        except Exception:
            slack_posted = False
    return {"drift": d.__dict__, "baseline": base.__dict__, "recent": recent.__dict__,
            "slack_posted": slack_posted}


@app.get("/api/agent/quality")
def agent_quality(samples: int = 8):
    """Grade recent agent answers and trend the quality score (the live judge)."""
    from chronolens.judge import grade_batch
    turns = _drive_agent(samples)
    if not turns:
        return JSONResponse({"error": "agent not reachable"}, status_code=502)
    answers = [t.get("answer", "") for t in turns]
    return grade_batch(answers, cfg)


@app.get("/api/forecast")
def forecast():
    """Fast server-side forecast (one SigNoz query, no sleeps) for the chart —
    so the projection the UI draws is the *same* trend the loop decides on."""
    try:
        from chronolens.foresee import forecast_from_series
        with SigNozClient(cfg) as sn:
            svcs = sn.list_services(window_seconds=300)
            svcs = [s for s in svcs if s.get("serviceName") and s.get("serviceName") != "chronolens"]
            if not svcs:
                return {"service": None}
            svcs.sort(key=lambda s: float(s.get("p99", 0) or 0), reverse=True)
            svc = svcs[0]["serviceName"]
            series = sn.service_p99_series(svc)
            err = 0.0
            try:
                err = sn.service_error_rate(svc)
            except Exception:
                pass
        fc = forecast_from_series(svc, series, cfg.p99_slo_ms, interval_s=15.0,
                                  error_rate=err, min_samples=cfg.min_samples,
                                  min_slope_ms_per_s=cfg.min_slope_ms_per_s)
        return {
            "service": svc, "slo_ms": cfg.p99_slo_ms, "current_p99_ms": fc.current_p99_ms,
            "slope_ms_per_s": round(fc.slope_ms_per_s, 2), "seconds_to_breach": fc.seconds_to_breach,
            "eta_low_s": fc.eta_low_s, "eta_high_s": fc.eta_high_s, "confidence": fc.confidence,
            "confident": fc.confident, "band_ms": fc.band_ms, "breaching": fc.breaching_now,
            "error_rate": fc.error_rate, "samples": fc.samples[-40:],
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/metrics_self")
def metrics_self():
    """Read ChronoLens's OWN emitted metrics back out of SigNoz (full-circle)."""
    try:
        with SigNozClient(cfg) as sn:
            return {
                "prevented_total": sn.metric_latest("chronolens.prevented_total"),
                "cost_saved_usd": sn.metric_latest("chronolens.cost_saved_usd"),
                "seconds_to_breach": sn.metric_latest("chronolens.seconds_to_breach"),
            }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/cooldown")
def cooldown():
    """Give capacity back once load has subsided, and attach the cost saved to
    the most recent incident (the closed-loop 'revert to save cost' step)."""
    try:
        from chronolens.cooldown import cool_down
        cd = cool_down(cfg, checks=2, interval_s=1.0)
        if cd.scaled_down:
            Ledger().update_last(
                scaled_down=True, capacity_before=cd.capacity_before,
                capacity_after=cd.capacity_after, cost_units_returned=cd.cost_units_returned,
                cooldown_note=cd.note,
            )
        return {"scaled_down": cd.scaled_down, "cost_units_returned": cd.cost_units_returned,
                "note": cd.note}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/respond")
def respond(managed: bool = True):
    """Run one ChronoLens loop. managed=false is the baseline (no-action) A/B arm."""
    try:
        with SigNozClient(cfg) as sn:
            return run_loop(sn, cfg, managed=managed)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ab")
def ab():
    """Run both arms of the A/B: baseline (no fix) then managed (ChronoLens on),
    so the UI can show the same fault breaching on one side and saved on the other."""
    try:
        with SigNozClient(cfg) as sn:
            baseline = run_loop(sn, cfg, managed=False)
            managed = run_loop(sn, cfg, managed=True)
        return {"baseline": baseline, "managed": managed}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/config")
def config_view():
    """Expose the governance / cost / LLM config so the UI can show trust + $."""
    return {
        "autonomy": cfg.autonomy,
        "trust_min_saves": cfg.trust_min_saves,
        "cost_per_unit_hr": cfg.cost_per_unit_hr,
        "llm_provider": cfg.llm_provider,
        "max_capacity": cfg.max_capacity,
        "min_dwell_s": cfg.min_dwell_s,
        "notify": bool(cfg.notify_webhook_url),
    }


@app.get("/api/signoz")
def signoz_status():
    """Live SigNoz integration status for the UI panel: guard alerts + firing
    count + notification channels. Best-effort; fails soft to disconnected."""
    try:
        with SigNozClient(cfg) as sn:
            rules = sn.list_rules()
            guard = [r for r in rules if isinstance(r, dict)
                     and (r.get("labels") or {}).get("chronolens") == "guard"]
            firing = sum(1 for r in guard
                         if str(r.get("state", "")).lower() in ("firing", "alerting"))
            channels = [c.get("name") for c in sn.list_channels()
                        if isinstance(c, dict) and c.get("name")]
        return {"connected": True, "guard_alerts": len(guard), "firing": firing,
                "channels": channels}
    except Exception as e:
        return {"connected": False, "error": str(e)}


_INBOX: list[dict] = []  # notifications received (from SigNoz channels / the loop)


@app.post("/webhook/sink")
async def webhook_sink(request: Request):
    """A receiver so SigNoz notification channels (and ChronoLens's own notify)
    have somewhere to deliver — makes the notification path end-to-end visible."""
    try:
        body = await request.json()
    except Exception:
        body = {"raw": (await request.body()).decode("utf-8", "replace")[:500]}
    _INBOX.append({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "body": body})
    del _INBOX[:-25]
    return {"ok": True}


@app.get("/api/inbox")
def inbox():
    return {"count": len(_INBOX), "recent": list(reversed(_INBOX))[:10]}


@app.get("/api/prevented")
def prevented():
    try:
        ledger = Ledger()
        return {
            "prevented": ledger.prevented_count(),
            "total": ledger.total_count(),
            "cost_units_saved": ledger.total_cost_units_saved(),
            "dollars_saved": ledger.total_dollars_saved(),
            "incidents": list(reversed(ledger.list()))[:20],
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/agent/circuit-break")
def agent_circuit_break(tool_name: str = "search_store"):
    """Circuit break a degraded AI agent tool."""
    from chronolens.steerage import ToolCircuitBreaker
    tb = ToolCircuitBreaker()
    tb.record_call(tool_name, latency_ms=4000.0, success=False)
    tb.record_call(tool_name, latency_ms=4000.0, success=False)
    tb.record_call(tool_name, latency_ms=4000.0, success=False)
    return {"ok": True, "tool_name": tool_name, "status": tb.get_status()}


@app.post("/api/agent/steer")
def agent_steer(tool_name: str = "search_store", reason: str = "looping"):
    """Inject dynamic steerage instruction to break an AI agent loop without losing context."""
    from chronolens.steerage import build_steerage_prompt
    prompt = build_steerage_prompt(tool_name, reason=reason)
    return {"ok": True, "steerage_prompt": prompt, "action": "injected_to_context"}


# --------------------------------------------------------------------------- #
# Breakthrough Feature APIs (Counterfactual, Throttle, MCP Copilot, Stress, CFO)
# --------------------------------------------------------------------------- #
@app.get("/api/counterfactual")
def get_counterfactual(service: str = "checkout-service"):
    """Dual-timeline chart data (unmitigated vs defused).

    NOTE: this is a **synthetic illustration** — it takes no SigNoz input. For the
    real, SigNoz-measured counterfactual use `/api/proof` (Chrono-Proof).
    """
    from chronolens.foresee import generate_counterfactual_projection
    out = generate_counterfactual_projection(service=service, slo_ms=cfg.p99_slo_ms)
    out["data_source"] = "synthetic"
    out["disclaimer"] = ("Illustrative shape only — not measured. Use /api/proof for the "
                         "SigNoz-measured counterfactual.")
    return out


@app.get("/api/proof")
def get_proof(service: str = "", window_seconds: int = 300, step_interval: int = 15):
    """CHRONO-PROOF — prove the outage that never happened, from real SigNoz data.

    Pulls the actual p99 series from SigNoz, fits the trend on the **pre-action**
    samples only, extrapolates the unmitigated path (+/- band), and overlays the
    **measured** post-action reality. Returns breach-seconds avoided, peak shaved,
    and error budget saved — every field labelled measured vs projected.
    """
    from chronolens.proof import proof_from_signoz
    try:
        with SigNozClient(cfg) as sn:
            svc = service
            if not svc:
                names = [s.get("serviceName") for s in sn.list_services(window_seconds=300)]
                names = [n for n in names if n and n != "chronolens"]
                if not names:
                    return JSONResponse({"ok": False, "error": "no services in SigNoz"},
                                        status_code=404)
                svc = max(names, key=lambda n: sn.service_p99_ms(n))
            p = proof_from_signoz(sn, cfg, svc, window_seconds=window_seconds,
                                  step_interval=step_interval)
        return p.to_dict()
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"proof unavailable: {e}"}, status_code=502)


@app.post("/api/agent/throttle")
def agent_throttle(enabled: bool = True, max_tokens: int = 256):
    """Dynamically cap agent context window and token budget across turns."""
    from chronolens.loopguard import apply_dynamic_throttle
    # also attempt notifying demo_agent if up
    try:
        httpx.get(f"http://localhost:8091/admin/throttle?enabled={str(enabled).lower()}&max_tokens={max_tokens}", timeout=1.0)
    except Exception:
        pass
    res = apply_dynamic_throttle(enabled=enabled, max_tokens=max_tokens)
    return {"ok": True, "throttle_state": res}


@app.get("/api/agent/throttle/status")
def agent_throttle_status():
    """Retrieve dynamic token circuit-breaker status."""
    from chronolens.loopguard import get_throttle_status
    return get_throttle_status()


@app.post("/api/mcp/chat")
async def mcp_chat(request: Request):
    """SigNoz MCP Natural Language Incident Co-Pilot query endpoint."""
    from chronolens.copilot import ask_signoz_copilot
    try:
        body = await request.json()
        user_query = body.get("query", "Why did checkout-service trigger an alert?")
    except Exception:
        user_query = "Summarize recent system reliability"
    return ask_signoz_copilot(user_query, cfg)


@app.post("/api/stress/run")
def run_stress_calibration(service_name: str = "checkout-service"):
    """Run self-calibrating micro-fault stress test and auto-tune guardrails."""
    from chronolens.stress import run_self_tuning_calibration
    res = run_self_tuning_calibration(cfg, service_name=service_name)
    return {"ok": True, "calibration": res}


@app.get("/api/cfo/report")
def get_cfo_report():
    """Generate executive SLA & financial ROI report for CFO and SRE leaders."""
    from chronolens.dollars import build_executive_cfo_report
    try:
        ledger = Ledger()
        records = ledger.list()
    except Exception:
        records = []
    return build_executive_cfo_report(ledger_records=records, cfg=cfg)


# --------------------------------------------------------------------------- #
# WhatsApp Business Cloud API Webhook & Control Endpoints
# --------------------------------------------------------------------------- #
@app.get("/webhook/whatsapp")
def whatsapp_verify(request: Request):
    """Meta WhatsApp Webhook Verification handshake."""
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and token == cfg.whatsapp_verify_token:
        from fastapi.responses import Response
        return Response(content=challenge, media_type="text/plain", status_code=200)

    return JSONResponse({"error": "Forbidden"}, status_code=403)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Inbound Meta WhatsApp Webhook: verifies HMAC signature and processes button clicks."""
    from chronolens.whatsapp_bot import process_whatsapp_button_click, verify_whatsapp_signature

    raw_body = await request.body()
    sig_header = request.headers.get("x-hub-signature-256")

    if not verify_whatsapp_signature(raw_body, sig_header, cfg.whatsapp_app_secret):
        return JSONResponse({"error": "Invalid signature"}, status_code=403)

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    # Process inbound interactive button replies async
    entries = data.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            val = change.get("value", {})
            messages = val.get("messages", [])
            for msg in messages:
                sender = msg.get("from", cfg.whatsapp_recipient_number)
                msg_type = msg.get("type")
                if msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    btn_reply = interactive.get("button_reply", {})
                    btn_id = btn_reply.get("id")
                    if btn_id:
                        threading.Thread(
                            target=process_whatsapp_button_click,
                            args=(btn_id, sender, cfg),
                            daemon=True,
                        ).start()

    return {"status": "ok"}


@app.post("/api/whatsapp/test")
def whatsapp_test_card(lang: str = "en-IN"):
    """Trigger a test WhatsApp interactive approval card (supports lang=hi-IN for Hindi)."""
    from chronolens.foresee import Forecast
    from chronolens.whatsapp_bot import post_whatsapp_approval

    fc = Forecast(
        service="checkout-service",
        current_p99_ms=480.0,
        slope_ms_per_s=18.5,
        seconds_to_breach=18.2,
        breaching_now=False,
        confidence=0.92,
        confident=True,
    )
    plan = {"action": "scale_out", "capacity_delta": 1}
    res = post_whatsapp_approval(fc, plan, cfg, lang=lang)
    return {"ok": True, "lang": lang, "whatsapp_response": res}


@app.get("/api/whatsapp/status")
def whatsapp_status():
    """Retrieve WhatsApp Cloud API integration status."""
    return {
        "enabled": cfg.whatsapp_enabled(),
        "phone_number_id": cfg.whatsapp_phone_number_id[:6] + "..." if cfg.whatsapp_phone_number_id else "",
        "recipient_number": cfg.whatsapp_recipient_number,
        "verify_token": cfg.whatsapp_verify_token,
    }


# --------------------------------------------------------------------------- #
# Sarvam AI Multilingual Endpoints
# --------------------------------------------------------------------------- #
@app.post("/api/sarvam/translate")
async def sarvam_translate(request: Request):
    """Translate incident text, WhatsApp messages, or CFO reports using Sarvam AI."""
    from chronolens.sarvam import translate_text
    try:
        body = await request.json()
        text = body.get("text", "Checkout service latency is climbing to SLO wall.")
        target_lang = body.get("target_lang", "hi-IN")
        source_lang = body.get("source_lang", "en-IN")
    except Exception:
        text = "Checkout service latency is climbing to SLO wall."
        target_lang = "hi-IN"
        source_lang = "en-IN"

    translated = translate_text(text, target_lang=target_lang, source_lang=source_lang, cfg=cfg)
    return {
        "ok": True,
        "original_text": text,
        "translated_text": translated,
        "target_lang": target_lang,
        "sarvam_enabled": cfg.sarvam_enabled(),
    }


if __name__ == "__main__":
    import uvicorn

    print("ChronoLens Mission Control -> http://localhost:8095")
    uvicorn.run(app, host="0.0.0.0", port=8095, log_level="warning")





