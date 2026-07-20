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
