# ChronoLens — demo video script

**Target length: 2:55** (the hackathon caps at 3:00).

**The running order is not ours to choose.** The submission form asks the video to cover, in
this order: **About the project → Tech stack and architecture → Live demo → Learning and
growth.** Every beat below sits inside one of those four acts, and the acts are in the form's
order. Don't reshuffle them to make the demo hit sooner.

Every number in the narration is one this build actually produced. Re-run the demo before
recording and **substitute your own live numbers** rather than reading these.

- [Before you hit record](#before-you-hit-record)
- [Pace check](#pace-check)
- [Act 1 · About the project](#act-1--about-the-project)
- [Act 2 · Tech stack and architecture](#act-2--tech-stack-and-architecture)
- [Act 3 · Live demo](#act-3--live-demo)
- [Act 4 · Learning and growth](#act-4--learning-and-growth)
- [Shot list](#shot-list-at-a-glance)
- [If something goes wrong](#if-something-goes-wrong-on-camera)
- [Alternate 60-second cut](#alternate-60-second-cut)

---

## Before you hit record

**Pre-flight (5 minutes).**

```bash
# 1. everything up, and prove it
python scripts/demo_check.py          # want: 23/23 checks passed

# 2. make the money shot real — inject, run the loop, then build the proof
curl -X POST "http://localhost:8090/admin/fault?mode=traffic-ramp&level=12"
#    wait ~90s for p99 to climb toward the 500ms SLO
python -m chronolens.cli respond      # want: "Outcome: breach avoided"
curl -X POST "http://localhost:8090/admin/fault?mode=off&level=0"
#    wait ~60s for recovery, then:
python -m chronolens.cli proof        # want: prevented=True, a non-zero "breach avoided"
```

**Windows and tabs**

- One Chrome window, tabs left to right: `1` Mission Control `localhost:8095` ·
  `2` SigNoz **Services** · `3` SigNoz **Traces** · `4` SigNoz **Dashboards** ·
  `5` SigNoz **Alerts** · `6` the architecture slide
  `localhost:8095/static/architecture.html` (Act 2 only).
- Pre-open the **Agent Watch** dashboard once so it's warm, then go back to the dashboard list.
  Set every SigNoz time picker to **Last 30 minutes**.
- Slack in its own window, on the ChronoLens channel, nothing else in frame.
- Zoom Chrome to **125%**. Judges watch on laptops.
- No editor needed. Act 2 uses the architecture slide in tab 6.

**Approve-to-act prep (Slack)**

This is the beat most likely to fail on camera, so set it up first and test it.

- Start the listener in a spare terminal: `python -m chronolens.cli slack`.
- Prove it before you record:
  ```bash
  python -m chronolens.cli slack test     # want: "sent", and the message in the channel
  ```
- Set `CHRONOLENS_AUTONOMY=suggest` in `.env` **and restart Mission Control** — autonomy is read
  at startup, so editing `.env` mid-run changes nothing. Record the autonomous loop beat first
  with `auto`, then restart in `suggest` for the approval beat. Two takes, spliced.
- Full-screen Slack on the ChronoLens channel and mute every other channel. Nothing else from
  your workspace should be in frame.
- Slack's Socket Mode dials outward, so there's no public URL, no tunnel and nothing that can
  expire mid-take. That's why the approval beat is filmed here.

**Recording:** 1080p minimum, system audio off, mic only. Speak ~15% slower than feels natural.

---

## Pace check

Every beat below is budgeted at **150 words per minute (2.5 words a second)**, which is a clear,
unhurried pace on camera. The deliberate silences — the CASCADE and VERIFY pauses, the tooltip hold,
the Slack rewrite — are counted separately, because they eat real seconds. That's why some beats run
longer than their word count alone would need.

| # | Beat | Window | Runs | Speech | Pauses | Words |
|---|---|---|---|---|---|---|
| 1 | The claim | 0:00 – 0:16 | 16s | 16s | — | 40 |
| 2 | How it's wired | 0:16 – 0:38 | 22s | 22s | — | 55 |
| 3 | Chrono-Proof | 0:38 – 1:04 | 26s | 24s | 2s (tooltip hold) | 60 |
| 4 | The loop, live | 1:04 – 1:32 | 28s | 24s | 4s (CASCADE, VERIFY) | 60 |
| 5 | Blast radius | 1:32 – 1:48 | 16s | 16s | — | 40 |
| 6 | Agent Watch | 1:48 – 2:04 | 16s | 16s | — | 40 |
| 7 | Approve-to-act | 2:04 – 2:30 | 26s | 22s | 4s (card read, rewrite) | 55 |
| 8 | SigNoz writes back | 2:30 – 2:44 | 14s | 14s | — | 35 |
| 9 | Close | 2:44 – 2:55 | 11s | 11s | — | 28 |
| | **Total** | | **2:55** | 2:45 | 10s | **413** |

If you find yourself rushing, cut a whole beat (the cut list is at the bottom). Don't speed-read —
it reads as panic on camera, and it's the fastest way to sound like you're hiding something.

Each beat below gives the **stage direction** first — window, scroll position, which element the
cursor touches, and when — then the **narration as one paragraph** you read straight through.
Timestamps inside a direction are moments *within* that beat.

---

## Act 1 · About the project

### [0:00 – 0:16] · runs 16s · The claim

**On screen**

- **Window:** tab 1 (Mission Control), 125% zoom, **scrolled fully to top** so the header and the
  four KPI chips are the only things in frame.
- **Before you talk:** hard-refresh (`Ctrl+Shift+R`) so the KPIs animate in from `—` instead of
  sitting there pre-filled. Wait for the header **SigNoz** pill to go green; if it's grey, SigNoz
  is unreachable and nothing below will populate.
- **In frame:** logo + "Predictive SRE · SigNoz closed loop"; the pills `SigNoz`, `MODE auto`,
  `SLO 500ms`; the two gradient chips (**Breach avoided**, **Incidents prevented**) and the two
  light cards (**Live p99**, **Capacity returned**).
- **Cursor:** parked off to the side, completely still, for all 16 seconds. This is a held frame.
- **0:13:** begin a slow scroll so the Chrono-Proof card is entering frame as you finish the last
  sentence.
- **Don't:** read the KPIs out loud, name the panels, or say "dashboard". The claim comes first;
  the UI tour never happens.

> Every reliability tool tells you an outage happened. ChronoLens tells you one was about to, takes a
> reversible action to stop it, and then proves from your own telemetry that it never landed. It's a
> closed loop built entirely on SigNoz, watching your infrastructure and your AI agents.
> *(40 words · 16s)*

---

## Act 2 · Tech stack and architecture

### [0:16 – 0:38] · runs 22s · How it's wired

There's **a built architecture slide for this beat** — one page, no editor, nothing to scroll:

```
http://localhost:8095/static/architecture.html
```

Open it as **tab 6** before you record. It's the same visual language as Mission Control, and it
already contains everything this beat claims: the four instrumented services, the OTLP arrow into
SigNoz, the reads arrow out to ChronoLens, the write-back rail underneath, the stack table, and the
real `casting.yaml` on the right. You are only pointing at things.

**On screen**

- **0:00:** switch to **tab 6** (the architecture slide). Whole page in frame — it's built to fit
  one screen at 125% zoom, so you should never need to scroll. If it doesn't fit, drop the zoom to
  100%.
- **0:04:** point at the **left box** ("3 demo services + 1 LLM agent") as you say "everything is
  OpenTelemetry", then slide right along the **OTLP arrow** into the dark **SigNoz + MCP** box.
- **0:12:** continue right along the **READS arrow** into the blue **ChronoLens** box.
- **0:15:** drop to the **write-back rail** (the pale blue strip that starts "↩ and it writes back")
  and hold there while you say "and writes back — dashboards, alerts, saved views, silences". This
  is the sentence that separates this project from a dashboard tour, so give it the extra beat.
- **0:19:** move to the **`casting.yaml` panel** on the right for the last sentence. No scrolling —
  the manifest is short enough to be fully visible, including `mcp: enabled: true`.
- **0:22:** switch back to **tab 1** so Act 3 opens on Mission Control.
- **Don't:** open your editor, a file tree, or a terminal in this act. 22 seconds disappears fast,
  and a `docker compose` scroll adds nothing a judge can read at speed.

**If you'd rather not use the slide,** the fallback is your editor full-screened on the architecture
block in `README.md` (the `demo store ──OTel──▶ SigNoz + MCP (Foundry)` diagram), then `casting.yaml`
in the same window — same pointing order. The slide exists because switching files mid-take is the
fiddliest thing in this script.

> Everything is OpenTelemetry. A three-service store and an LLM agent export traces, metrics and logs
> to SigNoz. ChronoLens reads them back through Query Builder v5 and the MCP server, and writes back —
> dashboards, alerts, saved views, silences. Python and FastAPI, instrumented itself, so its own loop
> shows up in SigNoz. And SigNoz comes up through Foundry from this committed `casting.yaml`.
> *(55 words · 22s)*

---

## Act 3 · Live demo

### [0:38 – 1:04] · runs 26s (24s speech + a 2s tooltip hold) · Chrono-Proof — proving a negative

**On screen**

- **Window:** tab 1. Scroll so the **Chrono-Proof — the outage that never happened** card fills
  the frame: title, the measured/projected legend, the chart, and the five stats underneath
  (**Measured peak · Projected peak · Breach avoided · Peak shaved · Confidence**) all visible at
  once. If the stats are cut off, scroll two more notches — the stats are the payoff.
- **Check the source pill** top-right of the card reads `signoz` before you talk. If not, click
  **Refresh** and wait.
- **0:04:** trace the **solid blue line** left-to-right as you say "measured".
- **0:08:** lift to the **amber dashed line** and trace it up and right as you say "projected".
  Leave the shaded confidence band visible — don't cover it with the pointer.
- **0:12:** hover and **hold** where the two lines separate, ~3 seconds, so the navy tooltip
  renders and both series read at the same timestamp. Don't jiggle; the tooltip flickers.
- **0:17:** drop to the **Breach avoided** stat as you say "ninety seconds", then one stat right
  to **Peak shaved**.
- **0:22:** rest on the note line under the stats for the closing sentence.
- **Don't:** click **Refresh** mid-shot. It blanks the chart for a second or two.

> Here's the problem with prevention: when it works, nothing happens. The solid blue line is measured,
> real p99 from SigNoz. The amber dashed line is projected — we fit the trend from before we acted and
> extrapolate it with a confidence band. The gap between them is what the fix bought: ninety seconds of
> breach avoided, four and a half seconds off the peak. Every field says measured or projected.
> *(60 words · 24s)*

*Verified run for reference: projected peak 4474ms ±1108, measured peak 48ms, 90s breach avoided,
4427ms peak shaved, confidence 71%. **Use your own numbers.***

---

### [1:04 – 1:32] · runs 28s (24s speech + two 2s pauses) · The loop, acting live

**On screen**

- **Window:** tab 1. Settle so the **Demo** button row *and* the **Closed loop** card are both in
  frame — click and consequence in one shot, no cut.
- **0:00:** click **Inject rising load**.
- **0:02:** click **Run ChronoLens** (the filled navy button), then scroll two notches so the
  stage pills and the `loop-state` pill are readable — it flips `idle` → `running`.
- **Then stop touching the mouse.** Cursor parked beside the card, never over the log (hovering
  scroll-hijacks it).
- **Read against the pills as they light:** LEARN → FORECAST → CASCADE → DECIDE → ACT → VERIFY →
  COOLDOWN. Pace to the pills, not to your reading speed.
- **Pause on CASCADE** (~2s): it prints the root hop and an exemplar trace ID. Let the trace ID
  land silently.
- **Pause on VERIFY** (~2s): let `loop-state` settle to its final value before you say the p99
  number.
- **0:25:** scroll up so **Capacity returned** is in frame — it now holds a dollar value.
- **Don't:** click **Run baseline (no fix)** or **Reset**. Baseline re-runs the whole thing and
  costs you 40 seconds.

> Now watch it work. It forecasts the breach behind a confidence guard, so it won't act on jitter. It
> names the root hop from real trace data and hands you the exemplar trace. It picks a reversible
> action — scale, because the signal is load; a slow dependency would be circuit-broken instead. Then
> it asks SigNoz whether the breach was actually avoided. Confirmed. And cooldown hands the capacity
> back. *(60 words · 24s)*

---

### [1:32 – 1:48] · runs 16s · Blast radius

**A minute before you record**, run this and leave it running:

```bash
curl -X POST "http://localhost:8090/admin/fault?mode=dependency-slow&level=40"
```

This one matters. With the traffic ramp instead, the *entry* service is what's degrading, so there's
nothing upstream to cascade to and you'll get a single victim.

**On screen — do exactly this**

1. On Mission Control, scroll down until the box titled **Blast radius** is on screen. It sits next
   to **Closed loop**, so it's a small scroll, not a tab switch.
2. Say your first sentence. Don't click yet.
3. Click **Forecast** in that box.
4. Wait about 2 seconds for the list to fill in.
5. Put the cursor on the **top line** — it should read `chronolens-payments-db`, hop
   `payment.db_query` — and leave it there while you say "payments-db is the root".
6. Move the cursor down the list one name at a time as you say each one: `chronolens-payments`, then
   `chronolens-store`.
7. Move the cursor onto the small grey tag that reads **`signoz-service-map`** and leave it there for
   your last sentence. That tag is the whole point of the beat.
8. Stop. Beat over.

**Bad take, don't use it:** if step 4 shows only one name, or the words
`topology_source: unavailable`, the fault is wrong or the service map hasn't refreshed yet. Wait 30
seconds, click **Forecast** again.

> One service breaching is a symptom. ChronoLens reads SigNoz's own dependency map and forecasts the
> order of failure: payments-db is the root, payments follows, then the storefront, each inheriting
> latency from the tier below. That topology is SigNoz's, derived from traces — not hardcoded.
> *(40 words · 16s)*

---

### [1:48 – 2:04] · runs 16s · Agent Watch

**On screen**

- **Window:** tab 1, whole **Agent Watch** card in frame — the `normal` / `drift` / `loop` mode
  buttons in the header and all three tiles (**Behaviour drift**, **Loop / cost breaker**,
  **Answer quality**).
- **Before this beat:** leave the agent in `normal` so the mode flip is visible on camera.
- **0:00:** click **loop**. The mode pill flips. Talk through the opening sentence while it runs —
  the breaker needs ~10 seconds of looping turns in SigNoz before it has anything to read.
- **0:10:** click **Check** on **Loop / cost breaker**.
- **0:12:** point at the numbers as you say them — the repeated tool `get_menu`, the repeat share,
  and steps-against-ceiling (`16 / 6`).
- **0:15:** move to the **`signoz`** badge and hold. If it reads `agent-driven` the logs are cold —
  say so out loud rather than glossing it, or re-record after the agent has run another minute.
- **Don't:** click **Grade**. It's slower and the narration already covers it.

> Agents fail in ways an HTTP status code never captures, so the same loop watches an LLM agent.
> Caught: sixteen calls to `get_menu`, no progress, sixteen steps against a six-step ceiling. And this
> badge is the point — that verdict came from reading the agent's GenAI spans out of SigNoz, and the
> quality judge reads full answers out of SigNoz logs. *(40 words · 16s)*

---

### [2:04 – 2:30] · runs 26s (22s speech + ~4s letting the card and the rewrite land) · Approve-to-act (Slack)

**On screen**

- **Setup, before this take:** Mission Control restarted with `CHRONOLENS_AUTONOMY=suggest`, Slack
  listener alive, Slack full-screened on the ChronoLens channel. This is a separate take from the
  autonomous loop beat — splice them.
- **0:00:** on tab 1, click **Inject rising load** then **Run ChronoLens**. The stage stream stops
  at **GOVERN** and the `loop-state` pill shows it's waiting on a human instead of acting. Point at
  that for one second — it's the honest half of the trust ladder.
- **0:05:** cut to **Slack**. The approval card is arriving: service, current p99, slope, ETA to
  breach, the proposed reversible action and its rollback, with **✅ Approve** and **✋ Deny**. Hold
  it for ~3 seconds and let the viewer actually read the card — this is the shot that sells the
  story, so don't rush it.
- **0:11:** click **✅ Approve**.
- **0:12:** the reply is **instant**, before any remediation runs — the card is replaced with
  "⏳ Applying `scale_out` on chronolens-store (approved by @you)…". Stay on it for a beat: that's
  what tells an approver the tap registered.
- **0:16:** the **same message rewrites itself again** with the final outcome — applied, SigNoz
  confirms p99 back under the SLO, breach avoided, rollback still available. Two rewrites of one
  message, no new notifications. Cut away too early and you lose the payoff.
- **0:24:** cut back to tab 1 and point at the newest row in the **Prevention ledger** — the receipt
  names the approver, so the decision is auditable after the fact.
- **Don't:** switch to any other messaging surface. One card, one tap, one channel.

> This is a live system, so the trust ladder can hold it back: suggest, earn, or auto. Here it's
> suggesting — and this is the part I like. It's three in the morning, you're not at your laptop, no
> VPN, no dashboard. The forecast, the fix and the rollback come to you, and one tap approves it. You
> get an answer instantly, then the verified outcome once SigNoz confirms p99 is back under the SLO.
> *(55 words · 22s)*

---

### [2:30 – 2:44] · runs 14s · SigNoz depth — it writes back

**On screen**

- **0:00:** switch to tab 4 (SigNoz **Dashboards**), list already on screen, and click
  **ChronoLens Agent Watch - chronolens-agent**. Five panels render: cost per turn, steps per
  turn, output tokens, tool calls by name, turn latency p99. Point at **Tool calls by name** —
  the grouped-by-`tool.name` bars show the loop you just triggered.
- **0:06:** switch to tab 5 (SigNoz **Alerts**) and point at the row starting
  **`ChronoLens anomaly -`**, specifically its state column reading **`firing`**. Hold there for
  the closing sentence. This is the strongest frame in the beat: SigNoz's own UI confirming a rule
  ChronoLens wrote through MCP.
- **Don't:** open a panel's edit view or the Query Builder. It looks like you're building it live,
  which undercuts the auto-filed claim.

> None of this was clicked together by hand. ChronoLens filed this GenAI dashboard, a cost threshold,
> and this anomaly rule against a learned baseline — already firing, because that cost spike was still
> inside budget but abnormal for this hour. *(35 words · 14s)*

---

## Act 4 · Learning and growth

### [2:44 – 2:55] · runs 11s · Close

**On screen**

- **0:00:** back to tab 1, scrolled to the very top so the frame matches the cold open — same
  header, same four KPI chips, except **Breach avoided**, **Incidents prevented** and **Capacity
  returned** now hold real numbers instead of `—`.
- **Cursor:** still. Hold the frame through the last sentence and for ~1 second after, so the
  video doesn't end on your mouse travelling to the stop button.

> The hard part wasn't predicting anything — it was proving a prevented outage without inventing the
> curve. That's why every field says measured or projected. One command brings the whole stack up
> through Foundry. Thanks for watching. *(28 words · 11s)*

---

## Shot list at a glance

| In | Runs | Act | Screen | Action | The one thing to land |
|---|---|---|---|---|---|
| 0:00 | 16s | 1 | Mission Control, top | held frame | prevention, not postmortems |
| 0:16 | 22s | 2 | tab 6 · architecture slide | point along the arrows | OTel in, SigNoz out, **writes back** |
| 0:38 | 26s | 3 | Chrono-Proof card | hover the crossover | measured vs projected, labelled |
| 1:04 | 28s | 3 | Demo row → Closed loop | Inject, Run | reversible action, SigNoz-verified |
| 1:32 | 16s | 3 | Blast radius | Forecast | root cause from SigNoz's service map |
| 1:48 | 16s | 3 | Agent Watch | loop → Check | `data_source: signoz` |
| 2:04 | 26s | 3 | Slack (full screen) | one tap Approve | 3am, no laptop → instant ack → verified |
| 2:30 | 14s | 3 | SigNoz Dashboards → Alerts | click through | it *writes*; anomaly `firing` |
| 2:44 | 11s | 4 | Mission Control, top | held frame | proving a negative, honestly |

---

## If something goes wrong on camera

| Problem | Say this, keep moving |
|---|---|
| Loop returns `pre-empted` / no breach | "It pre-provisioned from what it learned, so there's nothing to prevent — that's LEARN working." Reset capacity (`/admin/lever?action=scale&value=-4`) and re-inject. |
| Chrono-Proof shows `prevented=False` | Don't hide it: "the fault is still running, so p99 climbed again — it won't claim a save it can't measure." Turn the fault off, wait, refresh. |
| Slack card doesn't arrive | Check the listener terminal is alive, then `python -m chronolens.cli slack test`. |
| Tapping Approve does nothing | The listener died. Restart `python -m chronolens.cli slack` — the card stays valid, the button carries its whole payload. |
| Approve sits on "⏳ Applying…" | Verification is still running (it can take tens of seconds). Wait for the second rewrite; don't tap anything else. |
| Asked whether other channels work | Keep it short: "the approval engine is surface-agnostic; Slack is what we ship and demo." Don't open anything else on camera. |
| Loop acts instead of asking | You're still in `auto`. Set `CHRONOLENS_AUTONOMY=suggest` **and restart** Mission Control. |
| Blast radius shows 1 victim | Wrong fault. `mode=dependency-slow&level=40`, wait, Forecast again. |
| Agent verdict badge says `agent-driven` | Logs are cold. Say it out loud, or wait a minute and re-check. |
| A panel reads `—` | "SigNoz is still filling that window." Move on; don't debug on camera. |

---

## Alternate 60-second cut

Keep only: the Chrono-Proof chart (measured vs projected, breach-seconds avoided), one full loop
run ending on VERIFY, the Slack one-tap approval, and the auto-created SigNoz dashboard with the
firing anomaly alert. Drop Act 2, blast radius and Agent Watch.

**If the full cut runs long, drop in this order:** blast radius (1:32, buys 16s) → the `casting.yaml`
panel in Act 2 (say the Foundry line over the diagram instead, buys ~4s) → Agent Watch (1:48, buys
16s). Never drop Chrono-Proof, the approval tap, or the SigNoz writes — those are the three scored
moments.

---

## Don't forget

- **Declare AI-assistant usage in your submission.** Non-disclosure is disqualification.
- The four acts must stay in the form's order: About → Tech stack → Demo → Learning.
- Say **"SigNoz"** out loud early and often — "Best Use of SigNoz" is a scored criterion.
- Mention **Foundry + `casting.yaml`** at least once; reproducibility is a hard rule.
- Don't claim the AWS stack is deployed. It's a labelled scaffold.
