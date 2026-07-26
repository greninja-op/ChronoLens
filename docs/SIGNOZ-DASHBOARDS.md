# SigNoz dashboards & alerts that ChronoLens creates

ChronoLens doesn't just *read* SigNoz — it writes back. Every artefact below is created
by code, not clicked together by hand, so a prevented incident stays watched after the
loop moves on.

- [Import the JSON by hand (where to paste it)](#import-the-json-by-hand-where-to-paste-it)
- [One-command setup](#one-command-setup)
- [What gets created](#what-gets-created)
- [1 · Infra guard (auto-filed by the loop)](#1--infra-guard-auto-filed-by-the-loop)
- [2 · GenAI guard dashboard (Agent Watch)](#2--genai-guard-dashboard-agent-watch)
- [3 · Alert rules](#3--alert-rules)
- [Recreating them by hand](#recreating-them-by-hand-in-the-signoz-ui)
- [API constraints worth knowing](#api-constraints-worth-knowing)
- [Housekeeping](#housekeeping)

---

## Import the JSON by hand (where to paste it)

Both dashboards are committed as importable JSON, so you don't need to run ChronoLens to
get them into SigNoz:

| File | What it shows |
|---|---|
| `dashboards/chronolens-agent-watch.json` | GenAI guard — cost per turn, steps vs ceiling, output tokens, tool mix, turn latency |
| `dashboards/chronolens-guard.json` | Infra guard — service p99 with the SLO marker, plus ChronoLens's own `prevented_total` metric |

**Where to paste it** — in the SigNoz UI:

1. Left sidebar → **Dashboards**.
2. Click **+ New dashboard** (top right).
3. In the dialog, choose **Import JSON**.
4. Paste the whole contents of the `.json` file into the text box (or use **Upload** and pick
   the file), then confirm the import.
5. The dashboard appears in the list. Open it and set the time range to **Last 30 minutes**.

That's the only place JSON can be pasted — there's no per-panel import, and Grafana JSON is
not accepted. Reference: [Import Dashboard in SigNoz](https://signoz.io/docs/dashboards/import-dashboard/).
*Content rephrased for compliance with licensing restrictions.*

**Regenerate the files** after changing a panel in code, so the committed JSON can't drift:

```bash
python scripts/export_dashboards.py
```

**If a dashboard imports but renders empty** ("Welcome to your new dashboard"), the JSON is
missing `layout` or widget `id`s — see [API constraints](#api-constraints-worth-knowing). The
exported files always contain both.

**If a panel renders but says "No Data"**, the panel is fine and the window is wrong. Two cases:

| Panel | Why it can be empty | Fix |
|---|---|---|
| ChronoLens impact — incidents prevented | `chronolens.prevented_total` is ChronoLens's *own* gauge. It's published by a 20s heartbeat in Mission Control (`CHRONOLENS_METRICS_HEARTBEAT_S`), so it only exists while the app is running — and before that heartbeat existed it was written only during a loop run, one sample per run. | Make sure Mission Control is up, then widen the range to **Last 6 hours**, or run `python -m chronolens.cli respond` and refresh. |
| Agent Watch panels | The agent emits GenAI spans per turn. Cold agent, no data. | Let the agent self-drive for a minute (or flip it to `loop` mode), then refresh. |

Everything else on these dashboards reads span data from the demo services, which self-drive
continuously — those panels should never be empty with the stack up.

---

## One-command setup

With SigNoz up (`bash scripts/bringup.sh`) and `SIGNOZ_API_KEY` set in `.env`:

```bash
export PYTHONPATH=src

# Agent-side: GenAI dashboard + cost alert + anomaly rule
python -m chronolens.cli guard

# Infra-side: filed automatically whenever the loop prevents a breach
python -m chronolens.cli respond
```

Or over HTTP:

```bash
curl -X POST http://localhost:8095/api/guard/agent
```

Both paths are **idempotent in intent but not in effect** — SigNoz has no upsert for these,
so running them repeatedly creates duplicates. See [Housekeeping](#housekeeping).

---

## What gets created

| Artefact | Type | Created by | Signal |
|---|---|---|---|
| `ChronoLens guard - <service>` | Dashboard | the loop, on a prevented breach | traces + metrics |
| `ChronoLens guard - <service> p99 latency` | Threshold alert | the loop, on a prevented breach | traces |
| `ChronoLens guard - <service>` (saved view) | Traces-explorer view | the loop | traces |
| `ChronoLens Agent Watch - <agent>` | Dashboard | `cli guard` | traces |
| `ChronoLens guard - <agent> cost per turn` | Threshold alert | `cli guard` | traces |
| `ChronoLens anomaly - <agent> cost per turn …` | **Anomaly** alert | `cli guard` (via MCP) | metrics |

---

## 1 · Infra guard (auto-filed by the loop)

Built by `build_guard_dashboard()` in `src/chronolens/signoz.py`. Two panels:

| Panel | Query | Unit | Notes |
|---|---|---|---|
| `<service>` p99 latency | `p99(duration_nano)` filtered to `service.name = '<service>'` | `ns` | SLO drawn as a threshold marker, in **nanoseconds** — SigNoz stores span durations as `duration_nano`, so a threshold in ms renders in the wrong place |
| ChronoLens impact — incidents prevented | metric `chronolens.prevented_total`, `avg` over time, `max` across series | `short` | Reads back ChronoLens's **own** metric — the full-circle proof that saves are visible in SigNoz, not just in the local ledger |

---

## 2 · GenAI guard dashboard (Agent Watch)

Built by `build_agent_dashboard()`. This is the agent-side counterpart to the infra guard,
made from the OpenTelemetry **GenAI semantic-convention attributes** the agent emits.

| Panel | Query | Unit | Why it's here |
|---|---|---|---|
| Cost per turn (USD) | `avg(llm.cost_usd)` | `none` | Real money per turn; the budget is drawn as a threshold. The loop/cost breaker fires on this budget, not on a clock |
| Steps per turn | `max(llm.step_count)` | `short` | Ceiling marked. A rising step count with no new tools is a loop |
| Token usage (output) | `avg(gen_ai.usage.output_tokens)` | `short` | A silent jump here is usually how behaviour drift shows up first |
| Tool calls by name | `count()` grouped by `tool.name` | `short` | Reveals a tool the agent never used before, or one it now calls repeatedly |
| Turn latency p99 | `p99(duration_nano)` | `ns` | Deliberate contrast: latency can stay flat while behaviour drifts — which is exactly why the four panels above exist |

All panels filter on `service.name = '<agent service>'` (`chronolens-agent` by default,
override with `AGENT_SERVICE_NAME`).

---

## 3 · Alert rules

### Threshold rules (v2alpha1 schema → `POST /api/v2/rules`)

| Rule | Condition | Severity |
|---|---|---|
| `<service> p99 latency` | `p99(duration_nano)` **above** the SLO, `targetUnit: ms`, `at_least_once` in a 5m rolling window | warning |
| `<agent> cost per turn` | `avg(llm.cost_usd)` **above** `CHRONOLENS_AGENT_COST_BUDGET` | warning |

Both carry `labels.chronolens = "guard"`, which is how `/api/signoz` counts *ChronoLens's own*
guard rules rather than every rule in the workspace. At least one notification channel is
required by SigNoz — ChronoLens discovers an existing channel and attaches it.

### Anomaly rule (v1 schema → filed via MCP)

| Rule | Condition |
|---|---|
| `<agent> cost per turn deviates from its baseline` | metric `chronolens.agent.cost_usd`, `anomaly` function with `z_score_threshold: 2`, `seasonality: daily`, `algorithm: standard` |

A fixed threshold can't catch *"normal-looking but abnormal for this hour"* — a cost that
usually sits at $0.0002 drifting to $0.0008 is still under budget yet clearly wrong. The
anomaly rule compares against a learned daily baseline instead.

It needs the agent's **metrics**, which the demo agent emits every turn:

| Metric | Unit | Meaning |
|---|---|---|
| `chronolens.agent.cost_usd` | usd | cost of the latest turn |
| `chronolens.agent.steps` | 1 | tool steps in the latest turn |
| `chronolens.agent.output_tokens` | 1 | output tokens in the latest turn |

---

## Recreating them by hand (in the SigNoz UI)

If you'd rather build one manually — useful for understanding the queries:

**GenAI cost panel**
1. **Dashboards → New dashboard → New panel → Time series.**
2. Query type **Query Builder**, signal **Traces**.
3. Filter: `service.name = 'chronolens-agent'`.
4. Aggregation: `avg` on `llm.cost_usd`.
5. Y-axis unit: leave as `none` (it's dollars, not a byte/time unit).
6. **Thresholds →** add one at your cost budget (default `0.05`).

**Tool-mix panel** — same, but aggregation `count()` and **Group by** `tool.name`.

**p99 latency panel** — signal **Traces**, aggregation `p99` on `duration_nano`,
Y-axis unit **`ns`**. If you set the unit to `ms` the SLO marker lands in the wrong place.

**Anomaly alert** — **Alerts → New alert → Metrics**, pick `chronolens.agent.cost_usd`,
then switch the rule type to **Anomaly** and set the z-score. It won't offer anomaly for a
traces query (see below).

---

## API constraints worth knowing

Three things cost us rejected payloads, and none of them are in the error message:

1. **Anomaly rules only accept `METRIC_BASED_ALERT`.** A traces query is rejected with
   `anomaly_rule can only be used with METRIC_BASED_ALERT`. That's why the agent emits
   cost as a *metric* — spans alone can't be anomaly-alerted.
2. **The v2 endpoint rejects the v1 anomaly schema silently** — `POST /api/v2/rules`
   returns `{"message":"validation failed","errors":[]}` with an **empty** error list, so
   nothing tells you which field is wrong. ChronoLens files anomaly rules through the
   **MCP server's `signoz_create_alert`** tool instead, which handles the version
   difference (and means ChronoLens uses MCP for writes, not just reads).
3. **A dashboard can store panels and still render nothing.** The API accepts `widgets`
   without a `layout` array or widget `id`s, and the UI then shows "Welcome to your new
   dashboard" — it positions panels from `layout` (a react-grid spec keyed by widget id), and
   there was nothing to place. Same class of failure for fields the frontend maps over but the
   API doesn't require: `builder.queryFormulas`, `promql`, `clickhouse_sql`,
   `selectedLogFields`, `selectedTracesFields`, `contextLinks.linksData`, and the dashboard's
   own `variables`. Missing is `undefined`, not empty. `_hydrate_panel()` in `signoz.py` sends
   empties for all of them.
4. **Threshold markers need the long field names.** `{"index","label","value","unit"}` is
   accepted and silently draws nothing; the UI reads `thresholdValue`, `thresholdUnit`,
   `thresholdOperator`, `thresholdFormat` and `thresholdColor`.
5. **Latency thresholds are nanoseconds on dashboards, milliseconds on alerts.**
   Dashboard panels use `yAxisUnit: "ns"` with the marker in ns; alert rules take
   `target` in ms with `targetUnit: "ms"` and SigNoz converts internally.

---

## Housekeeping

SigNoz has no upsert for these artefacts, so **each run creates a new copy**. Before
recording a demo, prune duplicates so the Alerts list reads cleanly:

```bash
# list what exists (ChronoLens rules carry labels.chronolens = "guard")
python -m chronolens.cli mcp "are any alerts firing?"
```

Then delete extras in **Alerts → ⋯ → Delete**, keeping the newest of each name. The same
applies to dashboards under **Dashboards**.

Reference: builders live in `src/chronolens/signoz.py`
(`build_guard_dashboard`, `build_guard_alert`, `build_agent_dashboard`,
`build_agent_cost_alert`, `build_anomaly_alert`, `build_anomaly_alert_mcp_args`).
