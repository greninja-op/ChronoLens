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


@app.post("/api/agent/loopcheck")
def agent_loopcheck():
    """Drive one agent turn and run the loop guard on it (the cost-spiral breaker)."""
    from chronolens.loopguard import evaluate
    try:
        turn = httpx.get(f"{cfg.agent_url}/chat", timeout=12).json()
    except Exception as e:
        return JSONResponse({"error": f"agent not reachable: {e}"}, status_code=502)
    v = evaluate(turn.get("steps", 0), turn.get("tools", []), turn.get("cost_usd", 0.0),
                 max_steps=cfg.agent_max_steps, cost_budget=cfg.agent_cost_budget_usd,
                 repeat_threshold=cfg.agent_repeat_threshold)
    return {"turn": turn, "verdict": v.__dict__}


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
    return {"drift": d.__dict__, "baseline": base.__dict__, "recent": recent.__dict__}


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


if __name__ == "__main__":
    import uvicorn

    print("ChronoLens Mission Control -> http://localhost:8095")
    uvicorn.run(app, host="0.0.0.0", port=8095, log_level="warning")
