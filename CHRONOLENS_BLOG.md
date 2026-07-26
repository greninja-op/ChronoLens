# ChronoLens: proving the outage that never happened

**How we built a self-preventing reliability loop on SigNoz — and how we made it prove its own results with measured telemetry instead of a pretty chart.**

> Built for the **Agents of SigNoz** hackathon (Track 01 — AI & Agent Observability).
> Repo: [github.com/greninja-op/ChronoLens](https://github.com/greninja-op/ChronoLens)

<!-- IMAGE: hero — Mission Control dashboard, full window, Chrono-Proof chart visible.
     File: docs/images/dashboard.png  ·  Suggested caption: "ChronoLens Mission Control." -->

---

## The problem nobody can demo

Observability tells you what broke. Every SRE tool on the market is excellent at the postmortem
and useless at the ten seconds before it. So we built the obvious thing: predict the breach, act
before it lands, verify the fix.

Then we hit the problem that kills every prevention tool.

**Prevention is invisible.** When it works, nothing happens. There's no incident, no graph spike,
no war room — just a flat line and an engineer with no way to prove the flat line was earned. The
industry's usual answer is a "what would have happened" chart drawn from a formula, and anyone
technical can dismiss it in one sentence: *you made that curve up.*

We had exactly that in our own codebase. An endpoint called `/api/counterfactual` that produced a
beautiful dual-timeline chart out of a hardcoded exponential decay, with no telemetry behind it.
We deleted it.

What replaced it is the feature this post is really about.

---

## Chrono-Proof: a counterfactual made of measurements

The honest way to prove a negative is to be strict about which half of the claim is measured and
which half is estimated — and to say so on the artifact itself.

Chrono-Proof does five things:

1. Pulls the **real** p99 series for the service out of SigNoz (Query Builder v5, `time_series`).
2. Splits that series at the moment ChronoLens acted.
3. Fits the trend on the **pre-action samples only** — the same EWMA + Holt machinery the
   forecaster uses — and extrapolates it across the post-action window, with a confidence band
   derived from the residual spread.
4. Overlays the **measured** post-action reality from SigNoz.
5. Quantifies the gap: breach-seconds avoided, peak milliseconds shaved, and SLO-violation area
   (error budget) saved.

Here is real output from a live run, not a mock-up:

```text
=== CHRONO-PROOF: chronolens-store (source: signoz) ===

  MEASURED (SigNoz)   peak      48 ms ·     0s over SLO · final 45 ms
  PROJECTED (est.)    peak    4474 ms ±1108 ·   90s over SLO · trend +15.2 ms/s

  Breach avoided      90s
  Peak shaved         4427 ms
  Error budget saved  306490 ms·s
  Prevented           True  (confidence 71%)
```

Every number carries its provenance. The defused arm is `measured`. The counterfactual arm is a
**labelled linear extrapolation with an interval** — an estimate, and the note on the payload says
exactly that:

> The 'measured' arm is SigNoz data. The 'projected' arm is a linear extrapolation of the measured
> pre-action trend (± band) — a labelled estimate, not a measurement.

<!-- IMAGE: Chrono-Proof panel close-up — cyan measured line, amber dashed projection, SLO marker,
     and the five stats underneath. File: docs/images/chrono_proof.png -->

### The bug that made it honest

Our first version guessed *when* the action happened by taking the series peak. That broke in a
way worth documenting: while a load ramp was still running, p99 climbed again after the fix, the
"peak" landed in the wrong place, and Chrono-Proof reported **"the fix did not hold"** for a fix
that had held.

The correct answer was already in the system. Every remediation writes a case file to the ledger
with a timestamp, so the proof now derives the action point from the **recorded action time**:

```python
idx = int(round(n_samples - 1 - (age / step_s)))
```

It skips non-action rows (`none`, `pre-provision`, `suggest:*`), takes the newest real action, and
falls back to the peak heuristic only when no case matches the window — stating which anchor it
used. Six unit tests cover the arithmetic, the rejections and the fallback.

---

## Blast-radius: which service falls next

Predicting that *one* service will breach is table stakes. The question that actually matters in a
distributed system is the one nobody answers in advance:

> payment is about to go — what goes down with it, in what order, and how long do I have?

SigNoz already knows the topology. It derives a service dependency graph from traces and exposes
it at `/api/v1/dependency_graph`. We walk that graph upward from the degrading dependency, because
**a caller can never be faster than the thing it waits on**: a slow child pushes latency into
every ancestor, scaled by how much of the parent's traffic actually depends on that path.

Live output, three real services:

```text
=== BLAST-RADIUS FORECAST (topology: signoz-service-map) ===

  Root cause: chronolens-payments-db  [root hop: payment.db_query]

  service                     p99     slope  inherit   breach in
  chronolens-payments-db *  6824ms    +37.3     +0.0         NOW
  chronolens-payments       6824ms    +37.3    +37.3         NOW
  chronolens-store           951ms    +27.6    +27.6         NOW
```

Two details that make this real rather than decorative:

- **The root is the most-downstream degrading service.** A service climbing only because its
  dependency is slow is a *symptom*. Fixing it mutes the alarm and changes nothing.
- **Only services inside the dependency graph can be the root.** An unconnected sidecar with a
  steep slope isn't the cause of a cascade — it has no downstream blast path. (We found this by
  watching it confidently blame our demo AI agent, which nothing depends on.)

<!-- IMAGE: Blast-radius panel — root cause line + the ranked victim list with ETAs.
     File: docs/images/blast_radius.png -->

### One service can't cascade

This feature was untestable in our own demo at first: the store was a single service, so there was
nothing to chain. We split it into a real three-tier topology, each tier emitting spans under its
own `service.name` with the parent context preserved:

```
chronolens-store  ──▶  chronolens-payments  ──▶  chronolens-payments-db
```

Now `dependency-slow` injected at the deepest tier produces a genuine measured cascade, and SigNoz's
own dependency graph is what ChronoLens reads to trace it.

<!-- IMAGE: SigNoz's Service Map view showing the three-tier chain.
     File: docs/images/signoz_service_map.png -->

---

## The loop that does the work

Chrono-Proof and blast-radius are the evidence layer. Underneath is the control loop:

```
LEARN → FORESEE → CLASSIFY → CASCADE → GOVERN → PREVENT → VERIFY → COOLDOWN → RECORD
  ▲                                                                              │
  └──────────────────── the ledger becomes LEARN's memory ──────────────────────┘
```

- **LEARN** reads past incidents, including time-of-day seasonality. For a repeat offender it
  pre-provisions a higher floor *before* anything degrades, and it corroborates recurrence against
  SigNoz's own alert state rather than trusting only its local ledger.
- **FORESEE** projects p99 to a time-to-breach behind a **confidence guard**: enough samples, slope
  above a noise floor, and a *sustained* rise. An elevated error rate from a second, independent
  signal lifts confidence.
- **CLASSIFY** picks the fix that matches the signal, not always "scale": load → scale,
  dependency → circuit-break, pool → resize, memory → restart, errors → roll back. The `errors`
  signal is cross-checked against a SigNoz **logs** query, so classification spans two signals.
- **CASCADE** names the root hop from a grouped traces query, plus an exemplar trace ID for a
  deep link.
- **GOVERN** is a trust ladder — `suggest` (never acts alone), `earn` (autonomous after N verified
  saves on that service), `auto`.
- **PREVENT** acts behind anti-flap guardrails: a minimum dwell time between actions, a hard
  capacity ceiling, an hourly action budget, and a global kill switch. Every action is reversible
  and every action stores its precise inverse.
- **VERIFY** asks SigNoz whether the breach was actually avoided. If it wasn't, it rolls back and
  escalates.
- **COOLDOWN** returns the capacity once load subsides, so prevention isn't paid for with permanent
  over-provisioning.
- **RECORD** files the receipt that LEARN reads next time.

A run against live SigNoz, abridged:

```text
[FORESEE ] chronolens-store: p99 2540.8ms, rising 8ms/s → SLO breach NOW (confidence 100%)
[CLASSIFY] Signal: load → reversible fix 'scale'
[CASCADE ] Degradation at 'payment.charge' (p99 1005.1ms) (measured in traces) …
           Exemplar trace: a6c3d99cc80d5efc2dfa9f720cdbe773
[GOVERN  ] autonomy=auto — acting automatically
[PREVENT ] Applied 'scale' (reversible). Rollback: scale back down once load subsides
[VERIFY  ] Confirmed via SigNoz: p99 back to 53.5ms — breach avoided
[COOLDOWN] Load subsided — scaled 8.0 → 2.0, returned 6.0 capacity units (~$3.90)
[GUARD   ] Filed a guarding SigNoz alert + dashboard on chronolens-store p99
[RECORD  ] Case filed: breach avoided · returned 6.0 units (~$3.90)
```

<!-- IMAGE: the live loop panel mid-run, stages lighting up.
     File: docs/images/closed_loop.png -->

---

## Agent Watch: the same loop, pointed at an AI agent

Track 01 is agent observability, so ChronoLens watches an agent the way it watches a service — and
agents fail in ways HTTP status codes never capture.

The demo agent is a café assistant instrumented with **OpenTelemetry GenAI semantic-convention
attributes**. Each turn emits an `agent.turn` parent span with child `gen_ai.chat` and
`tool.execute` spans, carrying `gen_ai.request.model`, `gen_ai.usage.input_tokens` /
`output_tokens`, `llm.step_count`, `llm.cost_usd` and `agent.tools`. It runs in three modes —
`normal` (the learned baseline), `drift`, and `loop` — so each failure is reproducible on demand.

Three analyzers read those spans:

| Analyzer | The failure it catches |
| --- | --- |
| **Behaviour drift** | After a prompt tweak or model swap the agent still returns 200 OK with normal latency, but it now calls a tool it never used, takes more steps, or writes far longer answers. A fingerprint (tool distribution, model mix, avg steps, avg tokens) is scored against a saved baseline. |
| **Loop / cost breaker** | The agent reasons in circles, calling the same tool repeatedly, burning tokens with no crash. It fires on **no progress** and on a **cost budget**, not just a clock — so a long but genuinely productive turn is left alone. |
| **Answer quality** | Grades recent answers to separate *changed* from *worse* — drift is a change signal, not a verdict. The answers are read from **SigNoz logs**: the agent emits each full response as an OTel log record, because span attributes only carry a truncated preview and you cannot grade what you cannot read. |

### Detecting from SigNoz, not by poking the agent

This is the part we had to fix to be honest. The analyzers originally called the agent's `/chat`
endpoint to get turns — which means "agent observability" that never touched the observability
platform. Now the default path issues a **raw traces query** (`requestType: "raw"`) against SigNoz
for the agent's `agent.turn` spans and reconstructs the turns from their attributes:

```text
turns read FROM SIGNOZ: 16
   gpt-4o-mini  2 steps  ['get_menu', 'place_order']  $9e-05  src=signoz
```

Every response now reports `data_source: "signoz"`, and falls back to driving the agent only when
SigNoz has no spans yet (a cold stack) — saying so when it does.

Quality grading was the last hold-out, and fixing it needed a second signal rather than a cleverer
query: the agent now emits its **complete response as an OTel log record**, and the judge reads those
bodies back with a `requestType:"raw"` logs query. So the drift and loop analyzers read *traces*,
the judge reads *logs*, and all three are telemetry-driven — verified live on 8 graded answers.

<!-- IMAGE: Agent Watch section showing drift %, loop verdict and quality score.
     File: docs/images/agent_watch.png -->
<!-- IMAGE: SigNoz Traces explorer showing agent.turn / gen_ai.chat / tool.execute spans with
     GenAI attributes. File: docs/images/signoz_genai_traces.jpg -->

---

## Human-in-the-loop: Slack and WhatsApp

The trust ladder's `suggest` tier is only meaningful if a human can actually approve something. So
when GOVERN decides ChronoLens may not act alone, it posts an **interactive approval card**:

> 🕳️ **ChronoLens needs your approval**
> **Service:** `payment` · **Forecast:** p99 past SLO in ~85s (confidence 86%)
> **Signal:** pool · **Proposed fix:** `pool-resize` — *reversible*
> `[ ✅ Approve ]  [ ✋ Deny ]`

Tapping **Approve** runs the real PREVENT → VERIFY → COOLDOWN → RECORD path and then **edits the
same message** with the SigNoz-verified outcome ("p99 back to 53.5 ms — breach avoided"). Deny
records the decision and stands down. Agent anomalies get their own card with
**Break / pin baseline**, which pins the agent to its last-good baseline and verifies the next turn.

**Do you need both?** No — and we're explicit about it:

| Channel | Mechanism | When to use it |
| --- | --- | --- |
| **Slack** | Socket Mode (an outbound WebSocket), so **no public URL** is needed. Free tier is enough: a bot token (`xoxb-`) plus an app-level token (`xapp-`). | The default. Least friction, richest UI (Block Kit buttons), ideal for a team channel and for local development. |
| **WhatsApp** | Meta WhatsApp Cloud API webhooks with HMAC-SHA256 signature verification, interactive reply buttons. Needs a public HTTPS endpoint and a Meta business number. | Reach — an on-call engineer who isn't at a desk. Convenience, not capability. |

Either one alone is sufficient. They implement the same contract; Slack is the recommended path and
WhatsApp exists because approving a production fix from a phone lock screen is genuinely useful.

<!-- IMAGE: Slack approval card before and after tapping Approve (the message rewrite).
     File: docs/images/slack_approval.png -->
<!-- IMAGE: WhatsApp interactive approval card on a phone.
     File: docs/images/whatsapp_approval.png -->

### A note on the signature check

Our first implementation of the WhatsApp webhook returned `True` when the app secret or signature
header was missing — a development shortcut that accepts unsigned requests. It now **fails closed**
whenever a secret is configured: a missing signature is rejected. The only permissive case is local
development with no secret set at all, and the README says not to expose the webhook without one.
Worth flagging because it's the kind of shortcut that quietly ships.
---

## The telemetry stack: OpenTelemetry in, SigNoz out

Nothing in ChronoLens has a private data path. Everything it knows arrives as OpenTelemetry and
everything it concludes is written back to SigNoz.

**What we emit (OpenTelemetry):**

- The demo services export **OTLP traces** over gRPC (`:4317`) with `service.name` per service, so
  SigNoz derives the dependency graph itself rather than being told about it.
- The demo agent adds **GenAI semantic-convention attributes** — `gen_ai.request.model`,
  `gen_ai.usage.input_tokens` / `output_tokens`, plus `llm.step_count`, `llm.cost_usd`,
  `agent.tools` — on `agent.turn` / `gen_ai.chat` / `tool.execute` spans.
- ChronoLens instruments **itself**: each loop stage is a `chronolens.stage` span under one loop
  trace, and it exports its own **metrics** (`chronolens.prevented_total`, `cost_saved_usd`,
  `seconds_to_breach`). Its guard dashboard then reads those metrics back out of SigNoz — the loop
  watching the loop.

**What we read (SigNoz):**

| Surface | Used for |
| --- | --- |
| **Query Builder v5 — traces** (`scalar`, `time_series`, `raw`, `group_by`) | p99 per service, p99 series for forecasting and Chrono-Proof, per-span-name breakdown for the cascade root, and raw `agent.turn` spans for Agent Watch |
| **Query Builder v5 — logs** | `severity_text='ERROR'` counts that cross-check the `errors` classification against a second signal |
| **Metrics read-back** | ChronoLens's own gauges, so the dashboard closes the circle |
| **Service dependency graph** | The real topology behind the blast-radius forecast |
| **Exemplar trace IDs** | Deep links from a receipt into the exact trace |
| **Alert state / history** | LEARN confirms recurrence from SigNoz's firing rules, not just its local ledger |

**What we write (SigNoz):**

| Surface | Used for |
| --- | --- |
| **Threshold alert rules** | A guard alert per prevented incident, so it stays watched |
| **Dashboards** | A guard dashboard with a p99 panel and a panel reading ChronoLens's own metric |
| **Saved views** | A pinned Traces-explorer view for the guarded service |
| **Silences** | Muted while the loop actively remediates, lifted after VERIFY — nobody is paged for a fix already in flight |
| **Notification channels** | Discovered and reused, so ChronoLens routes its notes through the same channel an alert would |

### MCP: calling the server, not just resembling it

Foundry installs the **SigNoz MCP server** alongside SigNoz, and it's tempting to call your queries
"MCP-compatible" because they have the same shape. We did exactly that for a while — then admitted it
was a claim about resemblance, not usage, and wrote a real client.

`src/chronolens/mcp.py` is a dependency-free JSON-RPC client: it performs the `initialize` handshake,
sends `notifications/initialized`, lists the server's tools, and invokes them with `tools/call`.
Against the live server it reports `SigNozMCP`, protocol `2024-11-05`, and **41 tools**.

Four things the protocol taught us, none of them in our first guess:

- Auth is mandatory — no `SIGNOZ-API-KEY` header gets you `401 Authorization or SIGNOZ-API-KEY header required`.
- The `Accept` header must allow **both** `application/json` *and* `text/event-stream`, or the
  Streamable-HTTP transport refuses the request.
- A reply may arrive as an SSE frame (`data: {...}`) instead of a JSON body, so the parser handles both.
- Tool results are **JSON nested inside a text block** (`result.content[].text`) — a second decode.

The co-pilot then routes a plain-English question to real tool calls, and the UI lists every call with
its arguments and row count, so the answer is auditable rather than asserted:

```text
Q: which services are slowest right now?      → signoz_list_services            (5 rows)
Q: are any alerts firing?                     → signoz_list_alert_rules         (10 rows)
Q: any error logs in the last hour?           → signoz_search_logs              (1 row)
Q: top operations for chronolens-store        → signoz_get_service_top_operations (4 rows)
```

Routing is rule-based on purpose: intent here is a small closed set, an LLM would add latency and a
failure mode for no accuracy gain, and a reviewer can read the table and check it. We also removed an
LLM "phrasing" pass that had been rewriting correct answers into generic remediation prose — it turned
a true answer into a plausible-sounding wrong one, which is the exact failure this project exists to catch.

<!-- IMAGE: the MCP co-pilot panel showing an answer plus the tool calls it made.
     File: docs/images/mcp_copilot.png -->

The reads above still go through the REST Query Builder on the hot path, because the control loop
needs tight latency and deterministic shapes; MCP is how ChronoLens *answers questions*, and both
paths hit the same SigNoz.

---

## The demo app and the agent's model

Two things are watched, and it matters that we're precise about what's real.

**The demo store** is a synthetic multi-service app (store → checkout → payment, each its own
`service.name`) with two jobs: emit believable traces, and expose *reversible levers* — scale,
pool-resize, circuit-break, restart, roll back, reset. Its faults ramp gradually
(`traffic-ramp`, `dependency-slow`, `pool-leak`, `memory-leak`, `error-spike`) because a step
function isn't forecastable and a forecast you can't test isn't a forecast.

**The agent's model is simulated by default, and we say so.** The café assistant's three modes
(`normal` / `drift` / `loop`) produce deterministic token counts, tool sequences and costs from a
price table. That's a deliberate choice: a drift demo has to be *reproducible*, and a real model
that happens to answer consistently proves nothing. The spans it emits are real OpenTelemetry
GenAI spans either way, which is what the analyzers consume.

For real inference, `LLM_PROVIDER` switches the explanation layer and the agent to a live backend —
`openai`, `bedrock` (AWS), `azure`, or `gemini` — via one API key. With no key set, ChronoLens runs
end-to-end on a rule-based explainer. Nothing in the loop requires an LLM to function; the LLM only
makes the *narration* nicer, which is the right place for a non-deterministic component.

---

## Reproduce it

The hackathon asks for a reproducible install, so the repo ships `casting.yaml` +
`casting.yaml.lock` and **Foundry** brings up SigNoz *and* its MCP server in one command:

```bash
bash scripts/bringup.sh          # SigNoz UI :8080 · OTLP :4317/:4318 · MCP :8000/mcp
cp .env.example .env             # add SIGNOZ_API_KEY
pip install -r requirements.txt
python -m demo_store.store       # the watched services  :8090
python demo_agent/agent.py       # the watched agent      :8091
python app.py                    # Mission Control        :8095
```

Then drive it from the UI, or:

```bash
python -m chronolens.cli respond   # one full loop
python -m chronolens.cli proof     # the measured counterfactual
python -m chronolens.cli blast     # who falls next
python -m chronolens.cli slack     # the approval listener
```

---

## What we cut, and why it matters

Late on, we audited our own repo and deleted six features: a synthetic "counterfactual" chart that
drew a curve from a formula, a "stress test" that ran a hardcoded array and claimed to read SigNoz,
a tool circuit-breaker rebuilt on every request so it forgot instantly, an executive ROI report that
asserted "100% verification rate" as a string literal, a translation layer unrelated to
observability, and a token throttle nothing read.

They demoed fine. That's the problem — each one was a place where a judge opening the file would
find a claim the code didn't support, which poisons trust in the features that *are* real. Two
docstrings claimed "real-time OpenTelemetry span metrics from SigNoz" in modules containing no
SigNoz call at all.

The same pass fixed a webhook that accepted unsigned requests, an endpoint that returned its own
verify token, and a real-looking phone number committed as a default in source.

Fewer features, each of which survives being read. That's the trade we'd make again.

---

## Honest limits

- The **projected** arm of Chrono-Proof is a linear extrapolation of a measured trend, not a
  measurement. Real systems plateau under saturation, so a long projection is an upper bound. Every
  field is labelled by provenance and the confidence score falls as the pre-action trend gets noisier.
- All three Agent Watch analyzers now read SigNoz. Grading was the last hold-out: span attributes
  carry only a truncated preview of the response, so the agent ships each **full answer as an OTel
  log record** and the judge reads it back with a `requestType:"raw"` logs query
  (`data_source: "signoz"`, verified on 8 graded answers). If the logs pipeline is cold it falls
  back to driving the agent *and labels itself* `agent-driven` rather than implying telemetry.
- The **agent is simulated by default** (see above).
- The blast radius is only as good as the dependency graph — with a single service there is nothing
  to chain, and it says `topology_source: unavailable` rather than inventing edges.

---

## What we'd build next

Read `gen_ai.response` bodies from logs so quality grading is fully telemetry-driven; extend the
blast radius to rank by business impact rather than time-to-breach; and let LEARN tune the
confidence guard from its own false-positive history.

The idea we keep coming back to is the one this project started from: **an outage that never
happened should still leave evidence.** Everything else is plumbing.
