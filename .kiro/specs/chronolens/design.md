# Design — ChronoLens

## Overview

ChronoLens closes a reliability loop on top of SigNoz:
**learn → foresee → cascade → prevent → verify → cooldown → record**, where each
incident's receipt becomes the memory (LEARN) for the next run. It reads
telemetry through the SigNoz Query Builder v5 (MCP-compatible), acts through a
target's control API with only reversible actions, gives capacity back when the
spike passes (cost), and proves its saves with a durable ledger.

## Architecture

```
demo_store (OTel) ──▶ SigNoz + MCP (Foundry)
                          ▲     │  Query Builder v5 reads
                          │     ▼
                     ChronoLens closed loop
   learn ─▶ foresee ─▶ cascade ─▶ prevent ─▶ verify ─▶ cooldown ─▶ record
     ▲        │ reversible levers (HTTP)                              │
     │        ▼                                                       │
     │  demo_store /admin/lever  (scale up / scale down)              │
     └──────────────── ledger (JSON) feeds LEARN next time ──────────┘
                          │
                          ▼
                   Mission Control UI
```

## Components

- **demo_store/store.py** — the watched app. A rising-load latency model:
  `latency = BASE + max(0, demand - capacity) * PENALTY`. The `traffic-ramp`
  fault grows `demand` over time; the `scale` lever raises `capacity`. This
  makes the breach both *predictable* (gradual ramp) and *preventable* (scaling
  in time keeps latency flat). Emits `/order → cart → inventory → payment →
  payment.db_query → order.db_write` spans.

- **config.py** — env config (SigNoz URL/key, MCP URL, demo store URL, SLO).

- **signoz.py** — SigNoz client. Reads via Query Builder v5 for **traces**
  (`p99(duration_nano)`, incl. grouped-by-span-name breakdown) and **logs**
  (`count()` of `severity_text='ERROR'`); writes alerts, dashboards, and saved
  views; manages **silences** (create/delete); reads **alert state**
  (`list_rules` → firing guard rules). `_first_scalar` / `_series_by_group` walk
  the v5 response defensively. Errors become tagged `SigNozError`; every
  non-critical call is fail-open.

- **learn.py** — `recall(service)` reads the ledger; for a repeat offender it
  recommends a pre-provision floor and a wider lead window (act earlier). This
  is the memory that closes the loop.

- **foresee.py** — samples p99 N times, least-squares slope, projects
  time-to-breach; `worst_service` ranks all services.

- **cascade.py** — blast path + root hop. **Data-driven** when a SigNoz span
  breakdown is available (slowest measured span = root); falls back to the
  static store topology otherwise (`BlastPath.source` records which).

- **playbook.py** — `classify(cfg)` reads the dominant failure signal; `play_for(signal)`
  maps it to a reversible `Play` (load→scale, dependency→circuit-break,
  pool→pool-resize, memory→restart, errors→rollback). Turns ChronoLens from a
  one-trick autoscaler into a signal-matched remediator.

- **foresee.py** — samples p99, least-squares slope, projects time-to-breach,
  behind a **confidence guard** (`confidence_guard`: min samples, noise-floor
  slope, sustained-rise fraction) so it won't act on jitter.

- **prevent.py** — `propose` picks the playbook action for the signal; `apply`
  runs it through **anti-flap guardrails** then the selected **adapter**;
  `rollback` uses each action's *precise* inverse.

- **adapters.py** — the remediation backend behind one reversible-action
  interface: `DemoStoreAdapter` (HTTP levers, default), `KubernetesAdapter`
  (kubectl scale/rollout), `ShellAdapter` (configured command templates).

- **guardrails.py** — `FlapGuard`: file-backed per-service dwell timer, capacity
  ceiling, and an **action budget** (max actions/hour); state persists across runs.

- **locking.py** — `LoopLock`: a cross-process file lock (with stale detection)
  so two overlapping runs can't fight over the same target.

- **governance.py** — the trust ladder. `decide(cfg, service, ledger)` returns
  whether ChronoLens may act (`suggest` / `earn` after N proven saves / `auto`).

- **dollars.py** — `units_to_dollars`: values returned capacity in `$` via
  `cost_per_unit_hr` (the one place unit↔money math lives).

- **notify.py** — posts a prevented/escalated note to a Slack/webhook; fails open.

- **llm.py** — `explain(evidence)`: rule-based NL explanation, optionally enriched
  by OpenAI/Bedrock/Gemini; always falls back to rule-based.

- **metrics_self.py** — emits ChronoLens's own OTel gauges (prevented total,
  seconds-to-breach, cost saved) to SigNoz; fails open.

- **cooldown.py** — watches headroom; once the spike subsides, scales back to
  baseline and reports the capacity units returned (cost saved). Never scales
  down into a breach.

- **verify.py** — polls p99 through a grace window; verified iff it ends below
  SLO and trends down.

- **record.py** — append-only JSON `Ledger` of `CaseFile`s; prevented/total counts.

- **otel_self.py** — self-instrumentation; `stage_span` per stage under a loop
  trace; `flush()` for short-lived processes; fails open.

- **loop.py** — orchestrates the stages with self-tracing; `managed` vs
  `baseline` (A/B).

- **app.py + static/index.html** — Mission Control: live health chart (auto-zoom,
  smoothed, viewBox-matched to avoid text distortion), the loop stages, the
  "incidents prevented" scoreboard, Services and Prevented views, and the A/B
  controls.

## Data models

```
Memory(service, incident_count, recurrence, recommended_floor, lead_window_s, note)
Forecast(service, current_p99_ms, slope_ms_per_s, seconds_to_breach, breaching_now, samples)
Remediation(action, params, rollback, applied, result, error)
Verification(verified, final_p99_ms, peak_p99_ms, samples)
CoolDown(scaled_down, capacity_before, capacity_after, cost_units_returned, waited_s, note)
CaseFile(id, at, service, predicted_breach_in_s, p99_at_prediction_ms, slo_ms,
         action, rollback, verified, final_p99_ms, peak_p99_ms, outcome,
         load_onset_at, learning_applied, recommended_floor, prior_incidents,
         scaled_down, capacity_before, capacity_after, cost_units_returned,
         cooldown_note, evidence)
```

## Latency / prevention model (why it's honest)

Demand rises linearly with the fault; latency stays flat until demand exceeds
capacity, then climbs. ChronoLens forecasts the crossover and scales capacity
**before** it — so the line never reaches the SLO. Scaling is fully reversible.
The A/B runs the same fault with and without the action to prove causation.

## Error handling

- SigNoz failures → `SigNozError` (tagged, non-fatal).
- Remediation apply failure → recorded, loop continues.
- Verification failure → rollback + escalate.
- Span emission failure → logged and swallowed (fail open).

## Testing strategy

- Unit: slope math, breach projection, health-state classification, ledger I/O,
  reversible-action rollback, cascade path derivation.
- Integration: loop against a running SigNoz + demo store (managed vs baseline).
- Determinism for demo: the ramp is deterministic so the prediction reliably lands.

## Production target (AWS, serverless)

Scaffolded under `infra/` (AWS SAM): a scheduled **Lambda** runs `run_loop`
(EventBridge `rate(2m)`), records incidents to on-demand **DynamoDB**, and uses
**Bedrock** for NL explanations. Pay-per-use only. `CHRONOLENS_AUTONOMY=earn` in
prod so the loop earns trust before acting solo. See `infra/README.md`.
