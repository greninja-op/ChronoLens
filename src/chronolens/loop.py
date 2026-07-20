"""The ChronoLens loop: foresee → (cascade) → prevent → verify → record.

`run_loop(managed=True)` is the real thing: predict a breach, take a reversible
action, confirm it worked, and file the receipt. `managed=False` is the "without
ChronoLens" arm of the A/B — it forecasts and records what *would* have happened
but takes no action, so you can run the same fault twice and show the difference.
"""
from __future__ import annotations

import uuid

from .cascade import predict_blast_path
from .config import Config
from .foresee import worst_service
from .otel_self import flush, stage_span
from .prevent import apply, propose, rollback
from .record import Ledger, new_case
from .signoz import SigNozClient
from .verify import verify


def run_loop(sn: SigNozClient, cfg: Config, *, managed: bool = True,
             ledger: Ledger | None = None) -> dict:
    ledger = ledger or Ledger()
    loop_id = uuid.uuid4().hex
    timeline: list[dict] = []

    try:
        # --- FORESEE --------------------------------------------------
        with stage_span("foresee", loop_id):
            fc = worst_service(sn, cfg, polls=5, interval_s=2.0)

        if fc is None or not fc.predicted:
            timeline.append({"step": "FORESEE", "status": "ok",
                             "text": "No breach on the horizon. All services healthy."})
            return {"timeline": timeline, "managed": managed}

        eta = "NOW" if fc.breaching_now else f"~{fc.seconds_to_breach:.0f}s"
        timeline.append({
            "step": "FORESEE", "status": "warn",
            "text": f"{fc.service}: p99 {fc.current_p99_ms}ms, rising "
                    f"{fc.slope_ms_per_s:.0f}ms/s → SLO breach in {eta}.",
        })

        # --- CASCADE --------------------------------------------------
        blast = predict_blast_path("/order")
        timeline.append({"step": "CASCADE", "status": "info", "text": blast.narrative})

        outcome = "watch-only"
        rem = propose(fc.service)
        verified = False
        final_p99 = fc.current_p99_ms
        peak_p99 = fc.current_p99_ms

        if managed:
            # --- PREVENT ----------------------------------------------
            with stage_span("prevent", loop_id):
                rem = apply(cfg, rem)
            if rem.applied:
                timeline.append({
                    "step": "PREVENT", "status": "done",
                    "text": f"Auto-scaled {fc.service} (reversible). Rollback: {rem.rollback}",
                })
            else:
                timeline.append({"step": "PREVENT", "status": "warn",
                                 "text": rem.error or "remediation failed"})

            # --- VERIFY -----------------------------------------------
            with stage_span("verify", loop_id):
                v = verify(sn, fc.service, cfg.p99_slo_ms)
            verified, final_p99, peak_p99 = v.verified, v.final_p99_ms, v.peak_p99_ms
            if verified:
                outcome = "breach avoided"
                timeline.append({"step": "VERIFY", "status": "done",
                                 "text": f"Confirmed via SigNoz: p99 back to {final_p99}ms, "
                                         f"breach avoided."})
            else:
                outcome = "escalated"
                rolled = rollback(cfg, rem)
                timeline.append({"step": "VERIFY", "status": "warn",
                                 "text": f"Action didn't hold (p99 {final_p99}ms). "
                                         f"{'Rolled back and ' if rolled else ''}escalating to a human."})
        else:
            timeline.append({"step": "PREVENT", "status": "pending",
                             "text": "ChronoLens OFF (baseline run) — no action taken. "
                                     "This is the 'without me' arm of the A/B."})

        # --- RECORD ---------------------------------------------------
        with stage_span("record", loop_id):
            case = new_case(
                service=fc.service,
                predicted_breach_in_s=fc.seconds_to_breach,
                p99_at_prediction_ms=fc.current_p99_ms,
                slo_ms=cfg.p99_slo_ms,
                action=rem.action if managed else "none",
                rollback=rem.rollback if managed else "",
                verified=verified,
                final_p99_ms=final_p99,
                peak_p99_ms=peak_p99,
                outcome=outcome,
                evidence={"slope_ms_per_s": fc.slope_ms_per_s,
                          "samples": fc.samples,
                          "blast_root": blast.root},
            )
            ledger.record(case)
        timeline.append({"step": "RECORD", "status": "done",
                         "text": f"Case filed ({case.id}): {outcome}."})
        return {"timeline": timeline, "managed": managed, "case": case.id, "outcome": outcome}
    finally:
        flush()
