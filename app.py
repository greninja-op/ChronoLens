"""ChronoLens Mission Control — web UI + API.

Run (from the chronolens/ folder, with the demo store already running on :8090):
    set PYTHONPATH=src        (Windows)   /   export PYTHONPATH=src   (bash)
    python app.py
Then open http://localhost:8095
"""
from __future__ import annotations

import os
import sys

import httpx
from fastapi import FastAPI
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
