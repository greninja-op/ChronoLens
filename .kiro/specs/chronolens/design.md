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

- **signoz.py** — SigNoz client. Reads via Query Builder v5 (`p99(duration_nano)`
  traces queries); writes alerts/dashboards; `_first_scalar` walks the v5
  response defensively. Errors become tagged `SigNozError`.

- **learn.py** — `recall(service)` reads the ledger; for a repeat offender it
  recommends a pre-provision floor and a wider lead window (act earlier). This
  is the memory that closes the loop.

- **foresee.py** — samples p99 N times, least-squares slope, projects
  time-to-breach; `worst_service` ranks all services.

- **cascade.py** — topology-derived blast path; names the root hop.

- **prevent.py** — `propose` a reversible action; `apply`/`rollback`/`scale_by`
  via the store's `/admin/lever`.

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

Lambda (loop stages), EventBridge (SigNoz alert → loop), DynamoDB (ledger),
S3 (evidence), Bedrock (NL explanations), small Fargate (UI).
