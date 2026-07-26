# Agents of SigNoz — ChronoLens submission

**Track 1 · AI & Agent Observability** · solo/team form filled once.
Everything below is copy-paste ready. Fields marked **⬜ YOU** are the only ones I can't fill.

- [Form fields](#form-fields)
- [Project description](#project-description-copy-paste)
- [How we used SigNoz](#how-we-used-signoz-copy-paste)
- [AI-assistance declaration](#ai-assistance-declaration--mandatory)
- [Hackathon experience](#hackathon-experience-copy-paste)
- [Tech stack](#tech-stack)
- [What we deliberately did not ship](#what-we-deliberately-did-not-ship)
- [Checklist](#pre-submission-checklist)

---

## Form fields

| Field | Value |
|---|---|
| Email | **⬜ YOU** |
| Team name | **⬜ YOU** (your own name if solo) |
| Name of person submitting | **⬜ YOU** |
| Track | Track 1 — AI & Agent Observability |
| Project description | see [below](#project-description-copy-paste) |
| GitHub link | `https://github.com/greninja-op/ChronoLens` — public, ships `casting.yaml` + `casting.yaml.lock` |
| Deployed link | **⬜ YOU** — only paste a URL you've just loaded in a browser. If nothing is deployed, say "local one-command bring-up via Foundry; see README" rather than pasting a dead link |
| YouTube demo link | **⬜ YOU** — script in `docs/DEMO-SCRIPT.md` |
| How you used SigNoz | see [below](#how-we-used-signoz-copy-paste) |
| Project blog link | **⬜ YOU** — post `CHRONOLENS_BLOG.md`; must be a NEW blog, not the pre-blogging one |
| Hackathon experience | see [below](#hackathon-experience-copy-paste) |
| AI assistance | see [below](#ai-assistance-declaration--mandatory) — **non-disclosure is disqualification** |

---

## Project description (copy-paste)

```
ChronoLens is a closed-loop predictive SRE control plane built entirely on SigNoz.
Every reliability tool tells you an outage happened. ChronoLens tells you one is
about to, takes a small reversible action to stop it, and then proves from your own
telemetry that the outage never landed.

The loop is LEARN -> FORESEE -> CLASSIFY -> CASCADE -> GOVERN -> PREVENT -> VERIFY ->
COOLDOWN -> RECORD. It forecasts an SLO breach from real p99 traces behind a
confidence guard (enough samples, slope above a noise floor, a sustained rise, so it
never acts on jitter), names the root hop from trace data rather than the loudest
service, picks the reversible action that matches the signal (scale for load,
circuit-break for a slow dependency, roll back a bad deploy, resize a leaking pool),
then asks SigNoz whether the breach was actually avoided. If verification fails it
rolls itself back and escalates. Cooldown returns the capacity, valued in dollars, so
prevention isn't paid for with permanent over-provisioning.

Three capabilities make it more than autoscaling:

CHRONO-PROOF answers the hardest question in prevention: when it works, nothing
happens, so how do you prove anything? It pulls the real p99 series from SigNoz,
splits it at the action timestamp taken from the incident's own ledger entry, fits the
pre-action trend forward with a confidence band, and overlays measured reality. It
reports breach-seconds avoided, peak shaved and error budget saved — and every field
is labelled measured or projected, because an estimate is never presented as a
measurement.

BLAST RADIUS reads SigNoz's own service dependency map, finds the deepest service
that is actually degrading, propagates inherited latency upward and ranks victims by
time-to-breach. The topology is SigNoz's, derived from traces; if the endpoint isn't
available it says so instead of inventing edges.

AGENT WATCH applies the same loop to an LLM agent, because agents fail in ways an HTTP
status code never captures. Behaviour drift and a loop/cost breaker read the agent's
GenAI spans out of SigNoz; the answer-quality judge reads full response bodies out of
SigNoz logs, because span attributes only carry a truncated preview and you cannot
grade what you cannot read. Every verdict is labelled with its data source.

A trust ladder (suggest / earn / auto) decides whether ChronoLens may act alone. In
suggest mode it posts an interactive approval to Slack with the forecast, the proposed
reversible action and its rollback. One tap acknowledges instantly, then the same
message rewrites itself with the SigNoz-verified outcome. The ledger records who
approved it and on which surface. WhatsApp implements the same contract for whoever is
actually on call.

ChronoLens is itself OpenTelemetry-instrumented, so its own loop is a trace in SigNoz
and its own metrics are read back onto a dashboard it created. SigNoz and its MCP
server come up in one command through Foundry from the committed casting.yaml.
```

Short version, if the form limits length:

```
ChronoLens is a closed-loop predictive SRE control plane built on SigNoz. It forecasts
an SLO breach from real p99 traces behind a confidence guard, names the root hop from
trace data, takes a reversible action matched to the failure signal, and asks SigNoz
whether the breach was actually avoided — rolling itself back if not. Chrono-Proof then
proves the save from measured telemetry, with every field labelled measured or
projected. Blast radius forecasts the cascade from SigNoz's own service dependency map.
Agent Watch runs the same loop over an LLM agent, reading GenAI spans and log bodies
from SigNoz to catch drift, loops and cost spirals that a 200 OK hides. A trust ladder
routes anything it may not do alone to Slack for one-tap approval. ChronoLens is itself
instrumented, writes its own dashboards and alerts back into SigNoz (including an
anomaly rule filed through MCP), and comes up in one command via Foundry.
```

---

## How we used SigNoz (copy-paste)

```
SigNoz is not a dashboard bolted on the side — it is the only source of truth
ChronoLens has, and it both reads and writes.

READS (Query Builder v5 + MCP)
- Traces: p99 duration_nano per service drives every forecast; span-level attributes
  name the root hop; exemplar trace IDs are handed to the operator.
- Metrics: ChronoLens reads back its own emitted metrics (chronolens.prevented_total,
  cost_saved_usd, seconds_to_breach, capacity_units) plus the agent's cost, steps and
  token gauges.
- Logs: the answer-quality judge pulls full agent response bodies with a raw logs
  query, because span attributes only carry a truncated preview.
- Service dependency map: blast radius derives topology from SigNoz rather than
  hardcoding a graph, and labels the source (signoz-service-map vs unavailable).
- Alert state: LEARN checks whether guard alerts for a service are currently firing,
  so recurrence is confirmed from SigNoz and not just from the local ledger.

WRITES
- Dashboards: an infra guard dashboard (service p99 with the SLO marker in
  nanoseconds, plus the prevented_total read-back) and a GenAI Agent Watch dashboard
  (cost per turn against budget, steps against ceiling, output tokens, tool mix by
  tool.name, turn latency for contrast). Both are created by code, never clicked.
- Alert rules: threshold rules on service p99 and on agent cost per turn, plus an
  anomaly rule on chronolens.agent.cost_usd against a learned daily baseline — a fixed
  threshold cannot catch "still inside budget but abnormal for this hour".
- Saved views, notification channels, and alert silences: ChronoLens silences its own
  guard alert while it is remediating, so nobody is paged for a fix already in flight.

MCP SERVER (read and write)
A dependency-free JSON-RPC client speaks the real protocol — initialize,
notifications/initialized, tools/list, tools/call — against the SigNoz MCP server
installed by Foundry, and discovers 41 tools. Mission Control ships an "Ask SigNoz"
co-pilot that routes plain-English questions to real tool calls and shows every call
it made, so the answer is auditable. The anomaly alert rule is filed through MCP
because the v2 REST endpoint rejects the v1 anomaly schema with an empty error list —
so MCP is a write path, not just a read demo.

OPENTELEMETRY
Three demo services and an LLM agent export OTLP traces, metrics and logs. The agent
carries GenAI semantic-convention attributes (gen_ai.request.model,
gen_ai.usage.input_tokens / output_tokens) alongside llm.cost_usd, llm.step_count and
tool.name, and emits full responses as log records. ChronoLens instruments itself:
each loop stage is a span under one loop trace, so the agent that watches your
services is visible in SigNoz as a service itself.

FOUNDRY
SigNoz and its MCP server are installed from the committed casting.yaml with
`foundryctl cast -f casting.yaml` (wrapper: scripts/bringup.sh). casting.yaml.lock is
committed too, so judges can reproduce the exact deployment this was built against.
```

---

## AI-assistance declaration — MANDATORY

Non-disclosure is disqualification. Paste this, and edit it if the details differ:

```
AI assistants were used during this hackathon and are declared here in full.

Tools: Kiro (agentic IDE, Claude-based) as the primary pair-programmer; the SigNoz
MCP server was also driven by the assistant to create and inspect dashboards and
alert rules.

What they were used for: implementing features from my specifications, writing tests,
drafting documentation and the blog, and debugging live behaviour against a running
SigNoz instance.

What remained mine: the problem selection and product direction, the architecture and
the honesty rules the project is built on (measured vs projected labelling, no
synthetic counterfactuals, fail-closed webhook signatures), all review and acceptance
of generated code, and every decision about what to cut. Several features were removed
during the build precisely because they could not be defended.

Everything claimed in the submission was verified against a live SigNoz deployment,
not accepted on the assistant's word.
```

---

## Hackathon experience (copy-paste)

```
The hardest part wasn't predicting a breach — it was proving a prevented one. When
prevention works there is no outage to point at, and the tempting shortcut is to draw
a synthetic "what would have happened" curve. We built that, then deleted it, and
replaced it with a counterfactual fitted from real pre-action SigNoz samples where
every field is labelled measured or projected.

Most of the real bugs were only findable against live telemetry. A projection that
went negative. A noise-level slope hijacking the cascade root and discarding the real
service graph. A quality judge that couldn't grade answers because spans only carry a
truncated preview, which is why the agent now ships full responses as log records. An
LLM "phrasing" pass that was quietly overwriting correct MCP answers with generic
incident prose. Dashboards that stored their panels perfectly and rendered blank
because SigNoz positions panels from a layout array we hadn't sent.

We also learned three SigNoz API constraints the hard way: anomaly rules only accept
METRIC_BASED_ALERT, the v2 rules endpoint rejects the v1 anomaly schema with an empty
error list (so we file that rule through MCP instead), and latency thresholds are
nanoseconds on dashboards but milliseconds on alerts.
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Observability | SigNoz — Query Builder v5 (traces, metrics, logs), service dependency map, dashboards, alerts, saved views, silences |
| MCP | SigNoz MCP server (installed by Foundry); dependency-free JSON-RPC client, 41 tools, read **and** write |
| Instrumentation | OpenTelemetry SDK + Collector; GenAI semantic conventions; ChronoLens self-instrumented (traces + metrics) |
| Install / reproducibility | Foundry `foundryctl cast -f casting.yaml` (+ `casting.yaml.lock`) |
| ChronoLens | Python 3.9+, FastAPI, httpx |
| Mission Control | Server-rendered HTML + SSE live stage stream, vendored Chart.js, no build step |
| Human-in-the-loop | Slack Socket Mode approve-to-act (Block Kit); WhatsApp Cloud API implements the same contract |
| Demo workload | 3-tier demo store (store → payments → payments-db) + an LLM agent, both self-driving |
| Explanations | Rule-based by default; optionally enriched by OpenAI / Azure / Bedrock / Gemini — runs with no key |
| Tests | 179 tests (unit + property-based with Hypothesis), including regressions for every live bug found |

---

## What we deliberately did not ship

Worth saying out loud — it's a credibility asset, not an omission.

- **A synthetic counterfactual.** Deleted in favour of Chrono-Proof's measured one.
- **A CFO-style savings report** that asserted a 100% verification rate from hardcoded assumptions.
- **A tool circuit-breaker** that built fresh state per request, so it never actually broke anything.
- **An auto-tuning stress feature** whose docstring claimed SigNoz telemetry it never queried.
- **The AWS serverless deployment**, which is present as a scaffold and labelled "not deployed" in `infra/README.md`. Bedrock is deliberately not enabled, because with no credentials it would silently fall back to rule-based explanations and make the claim false.

---

## Pre-submission checklist

- [x] `casting.yaml` + `casting.yaml.lock` in repo root
- [x] SigNoz usage documented in `README.md` and `docs/SIGNOZ-DASHBOARDS.md`
- [x] Dashboards exported to `dashboards/*.json` so judges can import without running the project
- [x] 179 tests passing
- [ ] GitHub repo set to **public**
- [ ] YouTube demo recorded (≤ 3 min; About → Tech stack → Demo → Learning, in that order)
- [ ] Blog published (NEW — screenshot guide in `docs/SCREENSHOTS.md`)
- [ ] Deployed link verified in a browser, or replaced with the one-command bring-up note
- [ ] AI-assistance declaration pasted into the form
- [ ] Form submitted
