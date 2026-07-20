# Implementation Plan

## Overview

Build status for ChronoLens. Checked items are implemented in this repo and
verified either by the test suite or by live runs against the demo store. The
full loop against a live SigNoz is pending a fresh Foundry bring-up (deferred).

## Tasks

- [x] 1. Project scaffold (requirements.txt, requirements-dev.txt, pytest.ini, .env.example, .gitignore, config) — _Req 9_
- [x] 2. Demo store — 5 fault types + reversible levers, OTel spans — _Req 2, 6, 12_
  - [x] 2.1 `/order` fan-out spans (cart → inventory → payment → db)
  - [x] 2.2 gradual, forecastable faults: traffic-ramp/-wave, dependency-slow, pool-leak, error-spike, memory-leak
  - [x] 2.3 reversible levers: scale, circuit-break, pool-resize, restart, rollback, reset; `dominant_signal` exposed
- [x] 3. SigNoz client — Query Builder v5 reads, alert/dashboard writes, tagged errors — _Req 8_
- [x] 4. FORESEE — slope + time-to-breach, behind a confidence guard — _Req 1, 13_
- [x] 5. CASCADE — topology blast-path + root hop — _Req 5_
- [x] 6. CLASSIFY — playbook maps dominant signal → reversible lever — _Req 12_
- [x] 7. PREVENT — reversible action via store lever, behind anti-flap guardrails — _Req 2, 14_
- [x] 8. GOVERN — trust ladder (suggest / earn / auto) — _Req 15_
- [x] 9. VERIFY — poll p99 in grace window; verified iff under SLO and trending down — _Req 3_
- [x] 10. COOLDOWN — scale back to baseline when load subsides; cost in units + dollars — _Req 10, 16_
- [x] 11. RECORD — JSON ledger of rich case files; prevented/total + units + $ saved — _Req 4, 16_
- [x] 12. LEARN — repeat-offender pre-provision + act earlier + time-of-day seasonality — _Req 11_
- [x] 13. GUARD — auto-create SigNoz alert + dashboard on a prevented incident (`yAxisUnit:"ns"`) — _Req 8_
- [x] 14. NOTIFY — post prevented/escalated note to Slack/webhook, fail open — _Req 16_
- [x] 15. EXPLAIN — rule-based NL explanation, optional OpenAI/Bedrock/Gemini enrichment — _Req 17_
- [x] 16. Self-observability — stage spans under a loop trace + own OTel metrics; fail open — _Req 7, 17_
- [x] 17. CLI — services / foresee / respond [off] / ab / cooldown / prevented / config (UTF-8 safe) — _Req 1–4, 6, 10, 16_
- [x] 18. Mission Control UI — live chart, loop timeline, prevented scoreboard (units + $), side-by-side A/B view, config chip — _Req 4, 6, 10, 16_
- [x] 19. Tests — property-based (Hypothesis) + unit for slope, confidence, projection, ledger, dollars, seasonality, playbook, guardrails, governance, guard — _Req 1–17_
- [x] 20. AWS serverless scaffold — SAM: Lambda + EventBridge + DynamoDB + Bedrock — _Req 17_
- [x] 21. Foundry `casting.yaml` + `scripts/bringup.sh` one-command bring-up — _Req 9_
- [x] 22. README quickstart + ERROR-AND-FIXES log (clone-and-run) — _Req 9_
- [x] 23. Deep SigNoz surface — logs corroboration, data-driven cascade, alert silences around remediation, alert-state recurrence in LEARN, saved view + metrics-readback panel, exemplar trace (all fail-open) — _Req 18_

## Task Dependency Graph

Execution waves (each wave depends on the previous):

```json
{
  "waves": [
    { "wave": 1, "tasks": [1], "description": "scaffold + config" },
    { "wave": 2, "tasks": [2, 3, 16], "description": "watched app, SigNoz client, self-observability" },
    { "wave": 3, "tasks": [4, 5, 6], "description": "foresee (confidence guard), cascade, classify" },
    { "wave": 4, "tasks": [8, 7, 9], "description": "govern, prevent (guardrails), verify" },
    { "wave": 5, "tasks": [10, 11, 12, 13, 14, 15, 23], "description": "cooldown, record, learn, guard, notify, explain, deep-signoz" },
    { "wave": 6, "tasks": [17, 18, 19], "description": "CLI, UI, tests" },
    { "wave": 7, "tasks": [20, 21, 22], "description": "AWS scaffold, bring-up, docs" }
  ]
}
```

## Notes

- Verified live (without full SigNoz): slope forecast math, confidence guard,
  cascade root, reversible scale up/down, cooldown cost-return, ledger counts +
  cost total, learn repeat-offender floor, playbook classification, guardrails,
  trust ladder. Covered by the 37-test suite.
- Pending: the full loop against a live SigNoz after a fresh `foundryctl cast`
  (bring-up deferred by the user).
- Remaining polish (not build-blocking): demo video + AWS Builder Center blog.
