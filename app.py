"""ChronoLens Mission Control — web UI + API.

Run (from the chronolens/ folder, with the demo store already running on :8090):
    set PYTHONPATH=src        (Windows)   /   export PYTHONPATH=src   (bash)
    python app.py
Then open http://localhost:8095
"""
from __future__ import annotations

import os
import sys

import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(HERE, "static", "index.html"))


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
