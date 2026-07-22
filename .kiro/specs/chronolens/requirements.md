# Requirements — ChronoLens

## Introduction

ChronoLens is a self-preventing reliability loop built on SigNoz. It watches a
service's live telemetry, forecasts an SLO breach before it happens, takes a
small **reversible** action to prevent it, verifies via SigNoz that the breach
was avoided, and records a receipt so the prevented incident is provable. It
also predicts how a failure would cascade and points remediation at the root.

Track: **AI & Agent Observability**. Constraints: SigNoz-deep (Query Builder,
alerts/dashboards, MCP-compatible reads), Foundry-reproducible, AWS serverless
production target.

## Requirements

### Requirement 1 — Forecast a breach early (FORESEE)
**User story:** As an on-call engineer, I want ChronoLens to predict an SLO
breach before it happens, so I can act while it's still just a rising line.

#### Acceptance criteria
1. WHEN ChronoLens samples a service's p99 over a short window THEN it SHALL compute the rate of change and project a time-to-breach against the SLO.
2. IF the current p99 already meets or exceeds the SLO THEN ChronoLens SHALL report a breach "NOW".
3. IF the trend is rising and the projected breach is within the lead window THEN ChronoLens SHALL report the predicted seconds-to-breach.
4. WHEN the trend is flat or falling THEN ChronoLens SHALL report no predicted breach.
5. All reads SHALL be expressed as SigNoz Query Builder v5 traces queries.

### Requirement 2 — Prevent with a reversible action (PREVENT)
**User story:** As an operator, I want ChronoLens to only ever take undoable
actions, so autonomy is safe.

#### Acceptance criteria
1. WHEN a breach is predicted THEN ChronoLens SHALL choose a reversible remediation and describe its rollback.
2. WHEN remediation is applied THEN it SHALL be executed against the target's control API (the demo store's lever endpoint).
3. IF applying the remediation fails THEN ChronoLens SHALL record the failure and continue (no crash).
4. The system SHALL never take an irreversible action automatically.

### Requirement 3 — Verify via SigNoz (VERIFY)
**User story:** As an operator, I want ChronoLens to confirm the fix worked from
telemetry, not assume it.

#### Acceptance criteria
1. WHEN a remediation is applied THEN ChronoLens SHALL poll the service p99 through a grace window.
2. IF the service settles below the SLO and is trending down THEN ChronoLens SHALL mark the incident "breach avoided".
3. IF the service does not recover THEN ChronoLens SHALL roll back the action and mark the incident "escalated".

### Requirement 4 — Record the receipt (RECORD)
**User story:** As a stakeholder, I want proof of the outages that were
prevented, since a prevented outage is otherwise invisible.

#### Acceptance criteria
1. WHEN the loop completes THEN ChronoLens SHALL write a case file (service, predicted breach, p99 at prediction, action, rollback, verified, final/peak p99, outcome, evidence).
2. The ledger SHALL expose counts of prevented vs. total incidents.
3. The case file SHALL persist across runs.

### Requirement 5 — Cascade prediction
**User story:** As an engineer, I want ChronoLens to name the root a failure
will spread from, so I fix the cause not the symptom.

#### Acceptance criteria
1. WHEN a breach is predicted THEN ChronoLens SHALL derive the blast path from the service topology and identify the root hop.
2. The narrative SHALL state the propagation path and which hop to fix.

### Requirement 6 — A/B demonstrability
**User story:** As a presenter, I want to prove ChronoLens caused the save.

#### Acceptance criteria
1. The loop SHALL support a "managed" run (takes action) and a "baseline" run (forecasts + records, takes no action).
2. Running the same fault in both modes SHALL show a breach in baseline and a save in managed.

### Requirement 7 — Full-circle self-observability
#### Acceptance criteria
1. Each loop stage SHALL emit one OpenTelemetry span linked under a single loop trace, tagged with `chronolens.stage`.
2. Span emission SHALL fail open — a broken exporter SHALL never crash the loop.
3. Buffered spans SHALL be flushed before a short-lived process exits.

### Requirement 8 — SigNoz integration
#### Acceptance criteria
1. Reads SHALL go through `POST /api/v5/query_range` (Query Builder v5).
2. The client SHALL be able to create alert rules and dashboards.
3. Any SigNoz failure SHALL surface as a tagged error and never abort unrelated work.

### Requirement 9 — Reproducible bring-up
#### Acceptance criteria
1. The repo SHALL ship `casting.yaml` and a one-command bring-up (`scripts/bringup.sh`).
2. Foundry SHALL install SigNoz **and** its MCP server together.
3. A fresh clone SHALL be runnable by following README quickstart only.

### Requirement 10 — Cost-aware scale-down (COOLDOWN)
**User story:** As an operator, I want ChronoLens to give capacity back after the
spike so I'm not paying for idle headroom.

#### Acceptance criteria
1. WHEN a service is over-provisioned (headroom above a margin) and above baseline THEN ChronoLens SHALL scale it back toward baseline.
2. WHEN it scales down THEN it SHALL record the capacity units returned (cost saved).
3. IF the load is still elevated THEN ChronoLens SHALL hold the extra capacity and say so (never scale down into a breach).
4. The ledger SHALL expose total capacity units saved.

### Requirement 11 — Learn and adjust (LEARN)
**User story:** As an operator, I want ChronoLens to stop fighting the same fire
twice — it should adjust so a recurring incident stops happening.

#### Acceptance criteria
1. WHEN a service has prior incidents in the ledger THEN ChronoLens SHALL treat it as a repeat offender.
2. FOR a repeat offender ChronoLens SHALL pre-provision a higher baseline floor BEFORE any breach and act earlier (wider lead window).
3. The case file SHALL record whether learning was applied and how many prior incidents informed it.
4. The loop SHALL be closed: each incident's receipt becomes LEARN's memory for the next run.
5. WHEN prior incidents cluster around a recurring hour-of-day THEN ChronoLens SHALL detect that seasonality and flag when the window is imminent.

### Requirement 12 — Signal-matched remediation (PLAYBOOK)
**User story:** As an operator, I want the fix to match the failure, not always "scale up".

#### Acceptance criteria
1. WHEN a breach is predicted THEN ChronoLens SHALL classify the dominant signal (load, dependency, pool, memory, errors).
2. The system SHALL map each signal to a distinct reversible lever (scale, circuit-break, pool-resize, restart, rollback) and describe its rollback.
3. IF the signal is unknown THEN ChronoLens SHALL fall back to scale-out.

### Requirement 13 — Confidence guard
#### Acceptance criteria
1. ChronoLens SHALL NOT project a breach unless it has at least a minimum number of samples.
2. ChronoLens SHALL ignore trends whose slope is below a configurable noise floor.
3. ChronoLens SHALL require a sustained (mostly monotonic) rise before acting, and SHALL expose a confidence score.

### Requirement 14 — Anti-flap guardrails
#### Acceptance criteria
1. ChronoLens SHALL NOT act on the same service again within a configurable dwell window.
2. ChronoLens SHALL NOT scale a service past a configurable capacity ceiling, clamping the action if needed.
3. Guardrail state SHALL persist across process runs.

### Requirement 15 — Governance / trust ladder
**User story:** As an operator, I want autonomy to be earned, not assumed.

#### Acceptance criteria
1. In `suggest` mode ChronoLens SHALL only propose actions (human-in-the-loop), never apply them.
2. In `earn` mode ChronoLens SHALL act autonomously only after a configurable number of verified saves on that service; otherwise it SHALL suggest.
3. In `auto` mode ChronoLens SHALL act automatically.

### Requirement 16 — Cost in dollars + notifications
#### Acceptance criteria
1. Capacity units returned on cooldown SHALL be valued in dollars via a configurable per-unit hourly rate.
2. The ledger SHALL expose total dollars saved.
3. WHEN an actionable outcome occurs THEN ChronoLens SHALL post a human-readable note to a configured Slack/webhook, failing open if none is set.

### Requirement 17 — Pluggable explanations + self-metrics + serverless
#### Acceptance criteria
1. ChronoLens SHALL produce a rule-based NL explanation of every incident, optionally enriched by an LLM (OpenAI/Bedrock/Gemini) and always falling back to rule-based on failure.
2. ChronoLens SHALL emit its own OpenTelemetry metrics (prevented total, seconds-to-breach, cost saved) to SigNoz, failing open.
3. The repo SHALL ship a serverless AWS scaffold (Lambda + EventBridge + DynamoDB + Bedrock) expressing the pay-per-use production shape.

### Requirement 19 — Trustworthy autonomy, pluggable backends, reproducible run
**User story:** As an operator, I want the loop to be safe to run unattended, to
act on real infrastructure, and to be trivial to stand up.

#### Acceptance criteria
1. FORESEE SHALL smooth the series (EWMA + Holt trend) and report a confidence *interval*, corroborated by a second signal (error rate).
2. The UI chart SHALL draw the **server-computed** forecast (not a client-only guess), with a projected-breach marker, a warning band, and a "would-be" ghost line after a save.
3. The loop SHALL stream each stage live (SSE) so execution is visible in real time.
4. Remediation SHALL be pluggable via an adapter (demo / kubernetes / shell) behind one reversible-action interface, with precise per-action rollbacks.
5. The loop SHALL be safe unattended: a global kill switch, a per-service action budget, and a cross-process lock preventing overlapping runs.
6. Notifications SHALL route through a SigNoz notification channel when no direct webhook is set; the UI SHALL read ChronoLens's own metrics back from SigNoz.
7. The UI SHALL be offline-safe (front-end libraries vendored, no runtime CDN).
8. The repo SHALL bring the app tier up in one command (`docker compose up`) and ship a deployable AWS SAM scaffold (SSM-secured secret, vendored package).

### Requirement 18 — Deep SigNoz integration (logs, silences, saved views, data-driven cascade)
**User story:** As a SigNoz user, I want ChronoLens to use SigNoz broadly and
idiomatically, not just as a metric endpoint.

#### Acceptance criteria
1. CLASSIFY SHALL corroborate the `errors` signal with a SigNoz **logs** query (`count()` of `ERROR` logs), in addition to the trace/latency signal.
2. CASCADE SHALL derive the root hop from a **grouped traces query** (p99 by span name) when available, and fall back to static topology otherwise; the source SHALL be recorded.
3. WHILE actively remediating THEN ChronoLens SHALL **silence** the service's guard alert, and SHALL lift the silence after verification.
4. LEARN SHALL read SigNoz **alert state** to confirm recurrence, not only the local ledger.
5. On a prevented incident ChronoLens SHALL create a **saved Traces view** and a dashboard panel that **reads back its own metric**.
6. Every one of these SigNoz calls SHALL fail open — an unavailable endpoint SHALL degrade gracefully and never break the loop.
