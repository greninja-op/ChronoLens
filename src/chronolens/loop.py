"""The ChronoLens closed loop (loop engineering):

    LEARN → FORESEE → CLASSIFY → GOVERN → PREVENT → VERIFY → COOLDOWN → RECORD
      ▲                                                                    │
      └──────────────── the ledger feeds LEARN next time ──────────────────┘

- LEARN reads past incidents (incl. time-of-day seasonality) and, for a repeat
  offender, pre-provisions a higher floor *before* any breach and acts earlier.
- FORESEE predicts the breach behind a confidence guard (won't act on noise).
- CLASSIFY (the playbook) names the dominant signal and the reversible fix.
- GOVERN (the trust ladder) decides whether ChronoLens may act on its own yet.
- PREVENT takes the reversible action behind anti-flap guardrails.
- VERIFY confirms via SigNoz; COOLDOWN gives capacity back (saves $).
- RECORD files a rich receipt (signal, $, explanation, guard artifacts), which
  becomes LEARN's memory next time — and posts a NOTIFY to Slack/webhook.

`managed=False` is the baseline A/B arm: it forecasts and records what *would*
have happened but takes no action.
"""
from __future__ import annotations

import time
import uuid

from .cascade import predict_blast_path
from .config import Config
from .cooldown import cool_down
from .dollars import units_to_dollars
from .foresee import worst_service
from .governance import decide
from .learn import recall
from .llm import explain
from .locking import LoopLock
from .metrics_self import flush as flush_metrics
from .metrics_self import record_metrics
from .notify import build_message, notify
from .otel_self import flush, stage_span
from .prevent import apply, propose, rollback, scale_by
from .record import Ledger, new_case
from .signoz import (
    SigNozClient,
    SigNozError,
    build_guard_alert,
    build_guard_dashboard,
    build_guard_saved_view,
)
from .verify import verify


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe(fn, default):
    """Run a best-effort SigNoz read/write; never let it break the loop."""
    try:
        return fn()
    except Exception:
        return default


def run_loop(sn: SigNozClient, cfg: Config, *, managed: bool = True,
             ledger: Ledger | None = None) -> dict:
    ledger = ledger or Ledger()
    loop_id = uuid.uuid4().hex
    timeline: list[dict] = []
    load_onset_at = _now()

    # --- concurrency lock: only one loop touches the target at a time --------
    lock = LoopLock(ledger.root)
    if not lock.acquire():
        return {"timeline": [{"step": "LOOP", "status": "warn",
                              "text": "Another ChronoLens loop is already running — skipping this one."}],
                "managed": managed, "outcome": "skipped"}
    try:
        # --- FORESEE ---------------------------------------------------
        with stage_span("foresee", loop_id):
            fc = worst_service(sn, cfg, polls=5, interval_s=2.0)
        if fc is None:
            timeline.append({"step": "FORESEE", "status": "ok", "text": "No services to watch yet."})
            return {"timeline": timeline, "managed": managed}
        svc = fc.service

        # --- LEARN (memory + seasonality) ------------------------------
        with stage_span("learn", loop_id):
            mem = recall(svc, ledger)
        learning_applied = False
        if mem.is_repeat_offender or mem.seasonal_due_now:
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

        # Corroborate recurrence with SigNoz's OWN alert state (not just our ledger).
        fired = _safe(lambda: sn.alert_fired_count(svc), 0)
        if fired:
            timeline.append({"step": "LEARN", "status": "info",
                             "text": f"SigNoz shows {fired} guard alert(s) for {svc} currently firing — "
                                     f"recurrence confirmed from SigNoz, not just the ledger."})

        if not fc.predicted:
            note = f"{svc}: p99 {fc.current_p99_ms}ms — no breach predicted"
            if not fc.confident and fc.reason:
                note += f" (confidence guard: {fc.reason})"
            elif learning_applied:
                note += " (learned pre-provision holding it)."
            else:
                note += "."
            timeline.append({"step": "FORESEE", "status": "ok", "text": note})
            outcome = "pre-empted" if learning_applied else "healthy"
            _finish(ledger, loop_id, timeline, svc, fc, cfg, load_onset_at,
                    learning_applied, mem, managed, sn=sn,
                    action="pre-provision" if learning_applied else "none",
                    rollback_txt="", verified=True, final_p99=fc.current_p99_ms,
                    peak_p99=fc.current_p99_ms, outcome=outcome, cooldown=None,
                    signal="load", why="", confidence=fc.confidence,
                    autonomy_mode=cfg.autonomy, seasonal_hour=mem.seasonal_hour)
            _emit_metrics(ledger, fc, 0.0)
            return {"timeline": timeline, "managed": managed, "outcome": outcome}

        eta = "NOW" if fc.breaching_now else f"~{fc.seconds_to_breach:.0f}s"
        timeline.append({"step": "FORESEE", "status": "warn",
                         "text": f"{svc}: p99 {fc.current_p99_ms}ms, rising {fc.slope_ms_per_s:.0f}ms/s "
                                 f"→ SLO breach in {eta} (confidence {fc.confidence:.0%})."})

        # --- CLASSIFY (playbook) ---------------------------------------
        rem = propose(svc, cfg)
        timeline.append({"step": "CLASSIFY", "status": "info",
                         "text": f"Signal: {rem.signal} → reversible fix '{rem.action}'. {rem.why}"})

        # Corroborate the 'errors' signal from a SECOND source: SigNoz logs.
        err_logs = _safe(lambda: sn.error_log_count(svc), 0.0)
        if err_logs > 0:
            timeline.append({"step": "CLASSIFY", "status": "info",
                             "text": f"SigNoz logs corroborate: {int(err_logs)} ERROR log(s) on {svc} "
                                     f"in the last window."})

        # --- CASCADE (data-driven from trace span breakdown) -----------
        breakdown = _safe(lambda: sn.span_p99_breakdown(svc), {})
        blast = predict_blast_path("/order", breakdown or None)
        trace_id = _safe(lambda: sn.exemplar_trace_id(svc), None)
        cascade_txt = blast.narrative + (f" Exemplar trace: {trace_id}." if trace_id else "")
        timeline.append({"step": "CASCADE",
                         "status": "info" if blast.source == "traces" else "ok",
                         "text": cascade_txt})

        extra_evidence = {"cascade_source": blast.source, "error_logs": err_logs}
        if trace_id:
            extra_evidence["exemplar_trace_id"] = trace_id
        if breakdown:
            extra_evidence["span_breakdown"] = breakdown

        # --- explanation (rule-based, optionally LLM-enriched) ---------
        ex = explain({"service": svc, "signal": rem.signal, "action": rem.action,
                      "slope_ms_per_s": fc.slope_ms_per_s, "eta_s": fc.seconds_to_breach,
                      "blast_root": blast.root}, cfg)

        verified = False
        final_p99 = fc.current_p99_ms
        peak_p99 = fc.current_p99_ms
        cd = None
        outcome = "watch-only"
        silence_id = None

        # --- GOVERN (trust ladder + global kill switch) ----------------
        kill = managed and not getattr(cfg, "enabled", True)
        gov = decide(cfg, svc, ledger) if (managed and not kill) else None
        may_act = bool(managed and not kill and gov and gov.may_act)

        if kill:
            timeline.append({"step": "GOVERN", "status": "pending",
                             "text": "Kill switch ON (CHRONOLENS_ENABLED=off) — observing only, "
                                     f"would have applied '{rem.action}' ({rem.why})."})
            outcome = "disabled"
        elif managed and gov is not None and not gov.may_act:
            timeline.append({"step": "GOVERN", "status": "pending",
                             "text": f"{gov.reason} Suggested action: '{rem.action}' ({rem.why})."})
            outcome = "suggested"
        elif may_act:
            timeline.append({"step": "GOVERN", "status": "done", "text": gov.reason})

        if may_act:
            # --- SILENCE: mute the guard alert while we actively fix it -
            sil = _safe(lambda: sn.create_silence(svc, 5), None)
            silence_id = _silence_id(sil)
            if silence_id:
                timeline.append({"step": "SILENCE", "status": "done",
                                 "text": f"Muted {svc}'s guard alert for 5 min while remediating — "
                                         f"no human paged for a fix already in flight."})

            # --- PREVENT ----------------------------------------------
            with stage_span("prevent", loop_id):
                rem = apply(cfg, rem)
            if rem.blocked:
                timeline.append({"step": "PREVENT", "status": "warn",
                                 "text": f"Held by guardrails — {rem.block_reason}"})
                outcome = "held"
                _lift_silence(sn, silence_id, timeline)
            else:
                extra = (" " + " ".join(rem.notes)) if rem.notes else ""
                timeline.append({"step": "PREVENT",
                                 "status": "done" if rem.applied else "warn",
                                 "text": (f"Applied '{rem.action}' on {svc} (reversible). "
                                          f"Rollback: {rem.rollback}.{extra}"
                                          if rem.applied else (rem.error or "remediation failed"))})

                # --- VERIFY -------------------------------------------
                with stage_span("verify", loop_id):
                    v = verify(sn, svc, cfg.p99_slo_ms)
                verified, final_p99, peak_p99 = v.verified, v.final_p99_ms, v.peak_p99_ms
                if verified:
                    outcome = "breach avoided"
                    timeline.append({"step": "VERIFY", "status": "done",
                                     "text": f"Confirmed via SigNoz: p99 back to {final_p99}ms — breach avoided."})
                    # --- COOLDOWN (give capacity back) ----------------
                    with stage_span("cooldown", loop_id):
                        cd = cool_down(cfg)
                    dollars = units_to_dollars(cd.cost_units_returned, cfg) if cd else 0.0
                    extra_note = f" (~${dollars:,.2f})" if dollars > 0 else ""
                    timeline.append({"step": "COOLDOWN",
                                     "status": "done" if cd.scaled_down else "info",
                                     "text": cd.note + extra_note})
                else:
                    outcome = "escalated"
                    rolled = rollback(cfg, rem)
                    timeline.append({"step": "VERIFY", "status": "warn",
                                     "text": f"Action didn't hold (p99 {final_p99}ms). "
                                             f"{'Rolled back and ' if rolled else ''}escalating to a human."})
                # Lift the silence once the fix is graded — the alert watches again.
                _lift_silence(sn, silence_id, timeline)
        elif not managed:
            timeline.append({"step": "PREVENT", "status": "pending",
                             "text": "ChronoLens OFF (baseline) — no action. This is the 'without me' A/B arm."})

        if silence_id:
            extra_evidence["silence_id"] = silence_id

        timeline.append({"step": "EXPLAIN", "status": "info",
                         "text": f"{ex.text} [{ex.source}]"})

        dollars_saved = units_to_dollars(cd.cost_units_returned, cfg) if cd else 0.0
        notified = _maybe_notify(cfg, svc, outcome, rem.action, fc.seconds_to_breach,
                                 fc.current_p99_ms, final_p99, dollars_saved, timeline)

        _finish(ledger, loop_id, timeline, svc, fc, cfg, load_onset_at,
                learning_applied, mem, managed, sn=sn,
                action=rem.action if may_act else ("suggest:" + rem.action if outcome == "suggested" else "none"),
                rollback_txt=rem.rollback if may_act else "",
                verified=verified, final_p99=final_p99, peak_p99=peak_p99,
                outcome=outcome, cooldown=cd, blast_root=blast.root,
                signal=rem.signal, why=rem.why, confidence=fc.confidence,
                autonomy_mode=cfg.autonomy,
                proven_saves=gov.proven_saves if gov else 0,
                dollars_saved=dollars_saved, seasonal_hour=mem.seasonal_hour,
                explanation=ex.text, explanation_source=ex.source, notified=notified,
                extra_evidence=extra_evidence)
        _emit_metrics(ledger, fc, dollars_saved)
        return {"timeline": timeline, "managed": managed, "outcome": outcome}
    finally:
        lock.release()
        flush()
        flush_metrics()


def _maybe_notify(cfg, svc, outcome, action, eta_s, p99_before, p99_after,
                  dollars_saved, timeline) -> bool:
    """Post a Slack/webhook message on an actionable outcome. Never raises."""
    if outcome not in ("breach avoided", "escalated", "pre-empted"):
        return False
    msg = build_message(service=svc, outcome=outcome, action=action, eta_s=eta_s,
                        p99_before=p99_before, p99_after=p99_after,
                        dollars_saved=dollars_saved)
    res = notify(cfg, msg)
    if res.sent:
        timeline.append({"step": "NOTIFY", "status": "done",
                         "text": f"Posted a {outcome} note to the incident webhook."})
    elif cfg.notify_webhook_url:
        timeline.append({"step": "NOTIFY", "status": "info", "text": f"Notify skipped: {res.reason}"})
    return res.sent


def _silence_id(result) -> str | None:
    """Pull a silence id out of a SigNoz create_silence response (best-effort)."""
    if isinstance(result, dict):
        data = result.get("data", result)
        if isinstance(data, dict):
            for key in ("silenceId", "id", "uuid"):
                if data.get(key):
                    return str(data[key])
        elif isinstance(data, str) and data:
            return data
    return None


def _lift_silence(sn, silence_id, timeline: list[dict]) -> None:
    """Delete a silence once remediation is graded, so the alert watches again."""
    if not silence_id:
        return
    ok = _safe(lambda: (sn.delete_silence(silence_id), True)[1], False)
    if ok:
        timeline.append({"step": "SILENCE", "status": "info",
                         "text": "Lifted the alert silence — the guard is watching again."})


def _emit_metrics(ledger: Ledger, fc, dollars_saved: float) -> None:
    """Publish ChronoLens's own gauges to SigNoz (fails open)."""
    try:
        record_metrics(
            prevented_total=ledger.prevented_count(),
            seconds_to_breach=(fc.seconds_to_breach or 0.0),
            cost_saved_usd=dollars_saved,
        )
    except Exception:
        pass


def _finish(ledger, loop_id, timeline, svc, fc, cfg, load_onset_at,
            learning_applied, mem, managed, *, sn=None, action, rollback_txt,
            verified, final_p99, peak_p99, outcome, cooldown, blast_root="",
            signal="load", why="", confidence=1.0, autonomy_mode="auto",
            proven_saves=0, dollars_saved=0.0, seasonal_hour=None,
            explanation="", explanation_source="", notified=False,
            extra_evidence=None):
    """RECORD stage: write the rich case file (also LEARN's memory next time).

    On a *prevented* incident (managed run, outcome "breach avoided") this also
    auto-files a guarding SigNoz alert + dashboard so the incident stays watched.
    """
    evidence = {"slope_ms_per_s": fc.slope_ms_per_s, "samples": fc.samples,
                "blast_root": blast_root, "confidence": confidence}
    if extra_evidence:
        evidence.update(extra_evidence)

    # --- GUARD: keep a prevented incident watched in SigNoz --------------
    if managed and outcome == "breach avoided" and sn is not None:
        guard_refs = _install_guard(sn, cfg, svc, loop_id, timeline)
        if guard_refs:
            evidence.update(guard_refs)

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
            signal=signal,
            why=why,
            confidence=confidence,
            autonomy_mode=autonomy_mode,
            proven_saves=proven_saves,
            dollars_saved=dollars_saved,
            seasonal_hour=seasonal_hour,
            explanation=explanation,
            explanation_source=explanation_source,
            notified=notified,
            evidence=evidence,
        )
        ledger.record(case)
    saved = ""
    if case.scaled_down:
        saved = f" · returned {case.cost_units_returned} units"
        if case.dollars_saved:
            saved += f" (~${case.dollars_saved:,.2f})"
    timeline.append({"step": "RECORD", "status": "done",
                     "text": f"Case filed ({case.id}): {outcome}{saved}."})


def _artifact_ref(result, name: str) -> dict:
    """Best-effort reference (name + id if SigNoz returned one) for the ledger."""
    ref: dict = {"name": name}
    if isinstance(result, dict):
        data = result.get("data", result)
        if isinstance(data, dict):
            for key in ("id", "uuid", "rule_id", "ruleId"):
                if data.get(key) is not None:
                    ref["id"] = data[key]
                    break
    return ref


def _install_guard(sn: SigNozClient, cfg: Config, svc: str, loop_id: str,
                   timeline: list[dict]) -> dict:
    """Auto-create a guarding SigNoz alert + dashboard for a prevented incident.

    Fails open: a ``SigNozError`` (or any hiccup) is caught and downgraded to an
    informational timeline entry — the loop never crashes on a monitoring
    side-effect ("SigNoz failures → tagged, non-fatal").
    """
    refs: dict = {}
    try:
        # SigNoz requires >=1 notification channel on a rule — discover any
        # existing channel and route the guard to it (fail-open to none).
        channels = _safe(lambda: [c.get("name") for c in sn.list_channels()
                                  if isinstance(c, dict) and c.get("name")], [])
        with stage_span("guard", loop_id):
            alert = build_guard_alert(svc, cfg.p99_slo_ms, channels)
            dashboard = build_guard_dashboard(svc, cfg.p99_slo_ms)
            alert_res = sn.create_alert(alert)
            dash_res = sn.create_dashboard(dashboard)
            refs["guard_alert"] = _artifact_ref(alert_res, alert["alert"])
            refs["guard_dashboard"] = _artifact_ref(dash_res, dashboard["title"])
            # A saved Traces-explorer view too, so a human clicking through
            # lands on the right filter (best-effort — never blocks the guard).
            view_res = _safe(lambda: sn.create_saved_view(build_guard_saved_view(svc)), None)
            if view_res is not None:
                refs["guard_saved_view"] = _artifact_ref(view_res, f"ChronoLens guard - {svc}")
        view_txt = " + saved view" if "guard_saved_view" in refs else ""
        timeline.append({"step": "GUARD", "status": "done",
                         "text": f"Filed a guarding SigNoz alert + dashboard{view_txt} on {svc} p99 "
                                 f"(threshold at the {cfg.p99_slo_ms}ms SLO) — the prevented "
                                 f"incident stays watched. The dashboard also reads back "
                                 f"ChronoLens's own prevented-total metric (full-circle)."})
    except SigNozError as exc:
        timeline.append({"step": "GUARD", "status": "info",
                         "text": f"Guard not filed (SigNoz unavailable): {exc}. Loop continues."})
    except Exception as exc:  # fail open on anything else too
        timeline.append({"step": "GUARD", "status": "info",
                         "text": f"Guard not filed: {exc}. Loop continues."})
    return refs
