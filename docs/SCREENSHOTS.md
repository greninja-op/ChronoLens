# Blog screenshots — what to capture and how

The blog (`CHRONOLENS_BLOG.md`) has **12 image slots**, each marked with an
`<!-- IMAGE: … -->` comment naming the file it expects. This is the shot-by-shot
capture guide: what has to be running, where to click, and what has to be visible for
the shot to be worth including.

Save everything into `docs/images/` with the exact filenames below — the blog
references them literally.

**Capture basics (Windows)**

- `Win` + `Shift` + `S` → region snip → paste into Paint / Photos → **Save as PNG**.
- Browser zoom **110–125%**. Anything smaller is unreadable once a blog scales it down.
- Crop to the panel. A full 4K desktop screenshot of one small card is wasted space.
- Target ~1600px wide for full-window shots, ~1200px for single panels.
- Turn off other notifications before Slack/WhatsApp shots.
- **Don't** capture your `SIGNOZ_API_KEY`, Slack tokens, or the `.env` file. If a terminal
  is in frame, check the scrollback first.

**Prerequisites for all shots**

```bash
python scripts/demo_check.py     # want 23/23 — nothing below works with a cold stack
```

SigNoz UI on `:8080`, Mission Control on `:8095`, demo store `:8090`, agent `:8091`.

---

## 1 · `dashboard.png` — hero shot

**Where:** Mission Control, `http://localhost:8095`, scrolled to the top.

1. Run one full loop first so the KPIs aren't all `—`: `.\scripts\fault.ps1 ramp`, wait ~90s,
   `python -m chronolens.cli respond`, then `.\scripts\fault.ps1 off` and
   `python -m chronolens.cli proof`.
2. Hard-refresh (`Ctrl` + `Shift` + `R`).
3. Capture the **whole browser window** — header, the four KPI chips, and enough of the
   Chrono-Proof chart to show the two lines.

**Must be visible:** the green `SigNoz` pill, real numbers in **Breach avoided** and
**Incidents prevented**, and the chart. A hero shot with empty KPIs undersells everything.

---

## 2 · `chrono_proof.png` — the counterfactual

**Where:** Mission Control → **Chrono-Proof — the outage that never happened** card.

1. Confirm the card's source pill reads `signoz`. If not, click **Refresh**.
2. Hover the point where the measured and projected lines separate so the tooltip renders.
3. Capture the card only: title, legend, chart **with the tooltip open**, and the five stats
   (**Measured peak · Projected peak · Breach avoided · Peak shaved · Confidence**).

**Must be visible:** solid blue measured line, amber dashed projection with its band, and a
non-zero **Breach avoided**. This is the most important image in the blog — reshoot it until
the two lines and the gap between them are obvious.

---

## 3 · `blast_radius.png` — cascade forecast

**Where:** Mission Control → **Blast radius** card.

1. Make the deepest tier the cause, or you'll get one victim and a boring shot:
   `.\scripts\fault.ps1 dependency`
2. Wait ~60s, click **Forecast**.
3. Capture the card: root line, the ranked victim rows with ETAs, and the
   `signoz-service-map` tag.

**Must be visible:** root = `chronolens-payments-db` with hop `payment.db_query`, at least
2 victims, and the `signoz-service-map` tag. If it says `topology_source: unavailable`, wait
and click **Forecast** again — don't ship that shot.

---

## 4 · `signoz_service_map.png` — SigNoz's own topology

**Where:** SigNoz UI → **Services** → **Service Map** (left nav, under Services).

1. Time range **Last 30 minutes**.
2. Let the graph settle, then drag the nodes apart so the three-tier chain reads left to right.
3. Capture the graph area.

**Must be visible:** `chronolens-store` → `chronolens-payments` → `chronolens-payments-db`.
This is the proof the topology in shot 3 is SigNoz's, not ours.

---

## 5 · `closed_loop.png` — the loop mid-run

**Where:** Mission Control → **Closed loop** card.

1. Click **Inject rising load**, then **Run ChronoLens**.
2. Snip **while it's running** — ideally just as VERIFY lights up, so you catch earlier stages
   still visible in the stream above it.

**Must be visible:** the stage pills (LEARN → FORECAST → CASCADE → DECIDE → ACT → VERIFY →
COOLDOWN) and log lines including the CASCADE root hop and the exemplar trace ID.

---

## 6 · `agent_watch.png` — agent verdicts

**Where:** Mission Control → **Agent Watch** card.

1. Click **loop** in the card header, wait ~15s for looping turns to land in SigNoz.
2. Click **Check** on **Loop / cost breaker**, **Check** on **Behaviour drift**, and
   **Grade** on **Answer quality** so all three tiles hold verdicts.
3. Capture the whole card.

**Must be visible:** all three tiles filled, and the `signoz` data-source badge. If a badge
reads `agent-driven`, wait a minute and re-check — the badge is the honesty claim in that
section of the blog.

---

## 7 · `signoz_genai_traces.jpg` — GenAI spans

**Where:** SigNoz UI → **Traces** explorer.

1. Filter `service.name = 'chronolens-agent'`, time range **Last 30 minutes**.
2. Open one trace and expand the waterfall.
3. Click a `gen_ai.chat` span and open its **Attributes** tab.
4. Capture the waterfall **and** the attributes panel in one frame.

**Must be visible:** the `agent.turn` → `gen_ai.chat` → `tool.execute` hierarchy, plus GenAI
attributes (`gen_ai.usage.output_tokens`, `llm.cost_usd`, `llm.step_count`, `tool.name`).
Note the blog expects `.jpg` for this one.

---

## 8 · `slack_approval.png` — before and after the tap

**Where:** Slack, the ChronoLens channel.

1. Set `CHRONOLENS_AUTONOMY=suggest` in `.env` and **restart Mission Control** (autonomy is
   read at startup).
2. Start the listener: `python -m chronolens.cli slack`.
3. Inject load and run the loop — the approval card arrives instead of an action.
4. **Snip the card first** (Approve / Deny visible), then tap **Approve** and snip the *same*
   message again after it rewrites itself with the verified outcome.
5. Stitch the two crops into one image, top and bottom.

**Must be visible:** in the first crop, service / forecast / proposed reversible action; in
the second, the outcome line with the SigNoz-verified p99. The rewrite is the point.

---

## 9 · `whatsapp_approval.png` — the same card on a phone *(optional)*

**Skip this one unless the WhatsApp token is fresh.** The demo video films Slack only, and the blog
reads fine without this image — the WhatsApp section can stand on the Slack shot plus its own prose.
Only capture it if `POST /api/whatsapp/test` returns `ok: true`; a `401 / code 190` means the Meta
access token has expired and you need a new one first.

**Where:** WhatsApp on your phone (or WhatsApp Web).

1. Message the business number from your phone once — Meta only allows interactive sends
   inside a 24-hour window the user opens.
2. `curl -X POST http://localhost:8095/api/whatsapp/test` → expect
   `whatsapp_response.ok = true`. A `401 / code 190` means the access token has expired;
   generate a fresh one in the Meta dashboard and update `.env`.
3. Screenshot the card, then tap **✅ Approve Fix** and screenshot the two replies that follow
   (the immediate acknowledgement, then the verified outcome).
4. Crop out your phone number and any other chats.

**Must be visible:** the card header, the forecast numbers, and both buttons. Mirroring the
phone (Windows **Phone Link**, scrcpy, QuickTime) gives a much cleaner image than a photo.
The tap only closes the loop if a public callback URL is configured (`ngrok http 8095` →
set it in the Meta app); without one the card still arrives, but the button does nothing.

---

## 10 · `signoz_genai_dashboard.png` — the dashboard ChronoLens wrote

**Where:** SigNoz UI → **Dashboards** → **ChronoLens Agent Watch - chronolens-agent**.

1. If it doesn't exist: `python -m chronolens.cli guard`, or import
   `dashboards/chronolens-agent-watch.json` (**Dashboards → + New dashboard → Import JSON**).
2. Time range **Last 30 minutes**. Run the agent in `loop` mode for a minute first so the
   panels have shape instead of flat lines.
3. Capture all five panels.

**Must be visible:** cost per turn, steps per turn, output tokens, **tool calls by name**
(grouped bars — this is the one that shows the loop), and turn latency p99.

---

## 11 · `signoz_anomaly_alert.png` — the anomaly rule firing

**Where:** SigNoz UI → **Alerts** → the rules list.

1. The rule is `ChronoLens anomaly - chronolens-agent cost per turn …`, filed via MCP by
   `python -m chronolens.cli guard`.
2. Capture the list row showing its **state column reading `firing`**, or open the rule and
   capture the header with the state badge.

**Must be visible:** the rule name and `firing`. This is SigNoz's own UI confirming a rule
ChronoLens created through MCP — don't substitute a screenshot of the threshold rule.

---

## 12 · `mcp_copilot.png` — MCP tool calls, shown

**Where:** Mission Control → **Ask SigNoz — MCP co-pilot** card (bottom of the page).

1. Click the **are any alerts firing?** chip (or type a question and press **Ask**).
2. Wait for the answer and the tool-call list underneath it.
3. Capture the card including the source pill.

**Must be visible:** the question, the answer, and at least one expanded `tools/call` entry
with the tool name. The auditability is the claim; an answer with no visible tool call proves
nothing.

---

## Checklist

| # | File | Surface |
|---|---|---|
| 1 | `docs/images/dashboard.png` | Mission Control (full window) |
| 2 | `docs/images/chrono_proof.png` | Mission Control |
| 3 | `docs/images/blast_radius.png` | Mission Control |
| 4 | `docs/images/signoz_service_map.png` | SigNoz |
| 5 | `docs/images/closed_loop.png` | Mission Control |
| 6 | `docs/images/agent_watch.png` | Mission Control |
| 7 | `docs/images/signoz_genai_traces.jpg` | SigNoz |
| 8 | `docs/images/slack_approval.png` | Slack |
| 9 | `docs/images/whatsapp_approval.png` | WhatsApp *(optional — needs a fresh token)* |
| 10 | `docs/images/signoz_genai_dashboard.png` | SigNoz |
| 11 | `docs/images/signoz_anomaly_alert.png` | SigNoz |
| 12 | `docs/images/mcp_copilot.png` | Mission Control |

Efficient order: run one loop → shots 1, 2, 5, 12 (Mission Control) → switch the fault to
`dependency-slow` → shots 3, 4 → agent into `loop` mode → shots 6, 7, 10, 11 → restart in
`suggest` mode → shot 8 (and 9 only if WhatsApp is authenticating).
