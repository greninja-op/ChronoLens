# Tasks — ChronoLens

Status of the build. Checked items are implemented in this repo.

- [x] 1. Project scaffold (requirements.txt, .env.example, .gitignore, config) — _Req 9_
- [x] 2. Demo store with rising-load model, OTel spans, fault + reversible levers — _Req 2, 6_
  - [x] 2.1 `/order` fan-out spans (cart → inventory → payment → db)
  - [x] 2.2 `traffic-ramp` fault (gradual, forecastable)
  - [x] 2.3 `scale` / `restart` / `reset` levers with rollback
- [x] 3. SigNoz client — Query Builder v5 reads, alert/dashboard writes, tagged errors — _Req 8_
  - [x] 3.1 `list_services`, `service_p99_ms` (p99 traces query)
  - [x] 3.2 defensive v5 scalar extraction
- [x] 4. FORESEE — sample p99, least-squares slope, project time-to-breach — _Req 1_
- [x] 5. CASCADE — topology blast-path + root hop — _Req 5_
- [x] 6. PREVENT — reversible propose/apply/rollback via store lever — _Req 2_
- [x] 7. VERIFY — poll p99 in grace window; verified iff under SLO and trending down — _Req 3_
- [x] 8. RECORD — JSON ledger of case files; prevented/total counts — _Req 4_
- [x] 9. Loop orchestration — managed vs baseline (A/B), self-traced stages — _Req 6, 7_
- [x] 10. Self-observability — stage_span under a loop trace, flush on exit, fail open — _Req 7_
- [x] 11. CLI — services / foresee / respond [off] / prevented — _Req 1–4, 6_
- [x] 12. Mission Control UI — live chart, loop stages, prevented scoreboard, A/B controls, Services/Prevented views — _Req 4, 6_
- [x] 13. Foundry `casting.yaml` + `scripts/bringup.sh` one-command bring-up — _Req 9_
- [x] 14. README quickstart + ERROR-AND-FIXES log (clone-and-run) — _Req 9_

## Next (hackathon polish, not yet done)
- [ ] 15. Auto-create a guarding SigNoz alert + dashboard on a prevented incident (wire `signoz.create_alert` / `create_dashboard` into RECORD), with `yAxisUnit:"ns"` on latency panels.
- [ ] 16. Trace-informed cascade (per-span p99 grouped by name) instead of static topology.
- [ ] 17. Unit tests (slope, projection, ledger, rollback, cascade) + property tests.
- [ ] 18. AWS serverless deployment (Lambda/EventBridge/DynamoDB/S3) + `casting.yaml.lock`.
- [ ] 19. Bedrock NL explanations of predictions.
- [ ] 20. Demo video + blog on AWS Builder Center; declare AI-assistant usage.
