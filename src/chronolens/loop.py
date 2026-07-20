"""The ChronoLens closed loop (loop engineering):

    LEARN → FORESEE → CASCADE → PREVENT → VERIFY → COOLDOWN → RECORD
      ▲                                                          │
      └──────────────── the ledger feeds LEARN next time ────────┘

- LEARN reads past incidents and, for a repeat offender, pre-provisions a
  higher floor *before* any breach and acts earlier.
- FORESEE predicts the breach; CASCADE names the root it spreads from.
- PREVENT takes a reversible action; VERIFY confirms via SigNoz.
- COOLDOWN gives the capacity back once the spike passes (saves cost).
- RECORD files a rich receipt (load onset, learning, cost saved, outcome),
  which becomes LEARN's memory next time.

`managed=False` is the baseline A/B arm: it forecasts and records what *would*
have happened but takes no action.
"""
from __future__ import annotations

import time
import uuid

from .cascade import predict_blast_path
from .config import Config
from .cooldown import cool_down
from .foresee import worst_service
from .learn import recall
from .otel_self import flush, stage_span
from .prevent import apply, propose, rollback, scale_by
from .record import Ledger, new_case
from .signoz import SigNozClient
from .verify import verify


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_loop(sn: SigNozClient, cfg: Config, *, managed: bool = True,
             ledger: Ledger | None = None) -> dict:
    ledger = ledger or Ledger()
    loop_id = uuid.uuid4().hex
    timeline: list[dict] = []
    load_onset_at = _now()

    try:
        # --- FORESEE ---------------------------------------------------
        with stage_span("foresee", loop_id):
            fc = worst_service(sn, cfg, polls=5, interval_s=2.0)
        if fc is None:
            timeline.append({"step": "FORESEE", "status": "ok", "text": "No services to watch yet."})
            return {"timeline": timeline, "managed": managed}
        svc = fc.service

        # --- LEARN (memory-driven pre-provision) -----------------------
        with stage_span("learn", loop_id):
            mem = recall(svc, ledger)
        learning_applied = False
        if mem.is_repeat_offender:
            timeline.append({"step": "LEARN", "status": "info", "text": mem.note})
            if managed and mem.recommended_floor > 0:
                res = scale_by(cfg, mem.recommended_floor)
                if not res.get("error"):
                    learning_applied = True
                    timeline.append({"step": "LEARN", "status": "done",
                                     "text": f"Pre-provisioned +{mem.recommended_floor} capacity for {svc} "
                                             f"from past incidents — before any breach."})
        else:
            timeline.append({"step": "LEARN", "status": "ok", "text": mem.note})

        if not fc.predicted:
            timeline.append({"step": "FORESEE", "status": "ok",
                             "text": f"{svc}: p99 {fc.current_p99_ms}ms — no breach predicted"
                                     + (" (learned pre-provision holding it)." if learning_applied else ".")})
            # even a healthy pass gets recorded so LEARN keeps improving
            outcome = "pre-empted" if learning_applied else "healthy"
            _finish(ledger, loop_id, timeline, svc, fc, cfg, load_onset_at,
                    learning_applied, mem, managed, action="pre-provision" if learning_applied else "none",
                    rollback_txt="", verified=True, final_p99=fc.current_p99_ms,
                    peak_p99=fc.current_p99_ms, outcome=outcome, cooldown=None)
            return {"timeline": timeline, "managed": managed, "outcome": outcome}

        eta = "NOW" if fc.breaching_now else f"~{fc.seconds_to_breach:.0f}s"
        timeline.append({"step": "FORESEE", "status": "warn",
                         "text": f"{svc}: p99 {fc.current_p99_ms}ms, rising {fc.slope_ms_per_s:.0f}ms/s "
                                 f"→ SLO breach in {eta}."})

        # --- CASCADE ---------------------------------------------------
        blast = predict_blast_path("/order")
        timeline.append({"step": "CASCADE", "status": "info", "text": blast.narrative})

        rem = propose(svc)
        verified = False
        final_p99 = fc.current_p99_ms
        peak_p99 = fc.current_p99_ms
        cd = None
        outcome = "watch-only"

        if managed:
            # --- PREVENT ----------------------------------------------
            with stage_span("prevent", loop_id):
                rem = apply(cfg, rem)
            timeline.append({"step": "PREVENT",
                             "status": "done" if rem.applied else "warn",
                             "text": (f"Auto-scaled {svc} (reversible). Rollback: {rem.rollback}"
                                      if rem.applied else (rem.error or "remediation failed"))})

            # --- VERIFY -----------------------------------------------
            with stage_span("verify", loop_id):
                v = verify(sn, svc, cfg.p99_slo_ms)
            verified, final_p99, peak_p99 = v.verified, v.final_p99_ms, v.peak_p99_ms
            if verified:
                outcome = "breach avoided"
                timeline.append({"step": "VERIFY", "status": "done",
                                 "text": f"Confirmed via SigNoz: p99 back to {final_p99}ms — breach avoided."})
                # --- COOLDOWN (give capacity back) --------------------
                with stage_span("cooldown", loop_id):
                    cd = cool_down(cfg)
                timeline.append({"step": "COOLDOWN",
                                 "status": "done" if cd.scaled_down else "info",
                                 "text": cd.note})
            else:
                outcome = "escalated"
                rolled = rollback(cfg, rem)
                timeline.append({"step": "VERIFY", "status": "warn",
                                 "text": f"Action didn't hold (p99 {final_p99}ms). "
                                         f"{'Rolled back and ' if rolled else ''}escalating to a human."})
        else:
            timeline.append({"step": "PREVENT", "status": "pending",
                             "text": "ChronoLens OFF (baseline) — no action. This is the 'without me' A/B arm."})

        _finish(ledger, loop_id, timeline, svc, fc, cfg, load_onset_at,
                learning_applied, mem, managed,
                action=rem.action if managed else "none",
                rollback_txt=rem.rollback if managed else "",
                verified=verified, final_p99=final_p99, peak_p99=peak_p99,
                outcome=outcome, cooldown=cd, blast_root=blast.root)
        return {"timeline": timeline, "managed": managed, "outcome": outcome}
    finally:
        flush()


def _finish(ledger, loop_id, timeline, svc, fc, cfg, load_onset_at,
            learning_applied, mem, managed, *, action, rollback_txt, verified,
            final_p99, peak_p99, outcome, cooldown, blast_root=""):
    """RECORD stage: write the rich case file (also LEARN's memory next time)."""
    with stage_span("record", loop_id):
        case = new_case(
            service=svc,
            predicted_breach_in_s=fc.seconds_to_breach,
            p99_at_prediction_ms=fc.current_p99_ms,
            slo_ms=cfg.p99_slo_ms,
            action=action,
            rollback=rollback_txt,
            verified=verified,
            final_p99_ms=final_p99,
            peak_p99_ms=peak_p99,
            outcome=outcome,
            load_onset_at=load_onset_at,
            learning_applied=learning_applied,
            recommended_floor=mem.recommended_floor if learning_applied else 0.0,
            prior_incidents=mem.incident_count,
            scaled_down=bool(cooldown and cooldown.scaled_down),
            capacity_before=cooldown.capacity_before if cooldown else 0.0,
            capacity_after=cooldown.capacity_after if cooldown else 0.0,
            cost_units_returned=cooldown.cost_units_returned if cooldown else 0.0,
            cooldown_note=cooldown.note if cooldown else "",
            evidence={"slope_ms_per_s": fc.slope_ms_per_s, "samples": fc.samples,
                      "blast_root": blast_root},
        )
        ledger.record(case)
    saved = f" · returned {case.cost_units_returned} capacity units" if case.scaled_down else ""
    timeline.append({"step": "RECORD", "status": "done",
                     "text": f"Case filed ({case.id}): {outcome}{saved}."})
