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

**Pre-flight (5 minutes).** Run these from the `chronolens/` folder in PowerShell, with
`$env:PYTHONPATH='src'` set:

```powershell
# 1. everything up, and prove it
python scripts/demo_check.py          # want: 23/23 checks passed

# 2. make the money shot real — inject, run the loop, then build the proof
.\scripts\fault.ps1 ramp              # traffic-ramp, level 12
#    wait ~90s for p99 to climb toward the 500ms SLO
python -m chronolens.cli respond      # want: "Outcome: breach avoided"
.\scripts\fault.ps1 off               # clear the fault
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

Every beat is laid out the same way: **Say this** — one paragraph, read straight through — then
**Do this**, numbered steps in order, with the words you should be saying at each step quoted inline.
Read the paragraph once to get the shape, then just work down the steps.

---

## Act 1 · About the project

### [0:00 – 0:16] · runs 16s · The claim

**Say this**

> Every reliability tool tells you an outage happened. ChronoLens tells you one was about to, takes a
> reversible action to stop it, and then proves from your own telemetry that it never landed. It's a
> closed loop built entirely on SigNoz, watching your infrastructure and your AI agents.
> *(40 words · 16s)*

**Do this**

1. Before you hit record: open Mission Control, zoom to 125%, scroll to the very top, and
   hard-refresh (`Ctrl` + `Shift` + `R`) so the numbers animate in instead of sitting there.
2. Check the **SigNoz** pill in the header is green. Grey means SigNoz is unreachable — fix that
   before recording anything.
3. Start recording. Don't move the mouse. Read the whole paragraph over this held frame.
4. On the last sentence, start scrolling down slowly so the **Chrono-Proof** card is coming into
   frame as you finish.

**Don't** read the numbers out loud, name any panel, or say the word "dashboard". The claim comes
first; the UI tour never happens.

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

**Say this**

> Everything is OpenTelemetry. A three-service store and an LLM agent export traces, metrics and logs
> to SigNoz. ChronoLens reads them back through Query Builder v5 and the MCP server, and writes back —
> dashboards, alerts, saved views, silences. Python and FastAPI, instrumented itself, so its own loop
> shows up in SigNoz. And SigNoz comes up through Foundry from this committed `casting.yaml`.
> *(55 words · 22s)*

**Do this**

1. Switch to **tab 6** (the architecture slide). The whole page should be in frame without scrolling.
   If it doesn't fit, drop the browser zoom to 100%.
2. Put the cursor on the **left box** ("3 demo services + 1 LLM agent") — say *"everything is
   OpenTelemetry. A three-service store and an LLM agent export traces, metrics and logs to SigNoz."*
3. Slide right along the **OTLP** arrow into the dark **SigNoz + MCP** box, then keep going right
   along the **READS** arrow into the blue **ChronoLens** box — say *"ChronoLens reads them back
   through Query Builder v5 and the MCP server…"*
4. Drop the cursor onto the pale blue strip that starts **"↩ and it writes back"** and leave it there
   — say *"…and writes back: dashboards, alerts, saved views, silences."* Give this one an extra
   beat; it's the line that separates this from a dashboard tour.
5. Move the cursor onto the **`casting.yaml`** panel on the right for the last sentence. No scrolling
   needed — `mcp: enabled: true` is already visible.
6. Switch back to **tab 1** so the next beat opens on Mission Control.

**Don't** open your editor, a file tree, or a terminal here. 22 seconds goes fast, and a
`docker compose` scroll gives a judge nothing they can read at that speed.

**Fallback if you'd rather not use the slide:** your editor full-screened on the architecture block in
`README.md` (the `demo store ──OTel──▶ SigNoz + MCP (Foundry)` diagram), then `casting.yaml` in the
same window — same pointing order. The slide exists because switching files mid-take is the fiddliest
thing in this script.

---

## Act 3 · Live demo

### [0:38 – 1:04] · runs 26s (24s speech + a 2s tooltip hold) · Chrono-Proof — proving a negative

**Say this**

> Here's the problem with prevention: when it works, nothing happens. The solid blue line is measured,
> real p99 from SigNoz. The amber dashed line is projected — we fit the trend from before we acted and
> extrapolate it with a confidence band. The gap between them is what the fix bought: ninety seconds of
> breach avoided, four and a half seconds off the peak. Every field says measured or projected.
> *(60 words · 24s)*

**Do this**

1. Before recording: scroll so the **Chrono-Proof** card fills the frame — you need the chart *and*
   the five numbers under it (Measured peak · Projected peak · Breach avoided · Peak shaved ·
   Confidence) visible at the same time. The numbers are the payoff; if they're cut off, scroll two
   more notches.
2. Check the small tag at the card's top-right says `signoz`. If not, click **Refresh** and wait for
   it before you record.
3. Say *"Here's the problem with prevention: when it works, nothing happens."* Cursor still.
4. Trace the **solid blue line** left to right — say *"the solid blue line is measured, real p99 from
   SigNoz."*
5. Trace the **amber dashed line** up and to the right — say *"the amber dashed line is projected…"*
   Don't cover the shaded band around it with the pointer.
6. Hover the point where the two lines separate and **hold it still for ~3 seconds** so the tooltip
   appears. Don't jiggle the mouse or it flickers.
7. Drop the cursor to the **Breach avoided** number — say *"ninety seconds of breach avoided"* — then
   move one number right to **Peak shaved** — *"four and a half seconds off the peak."*
8. Move to the grey text line under the numbers for the last sentence: *"every field says measured or
   projected."*

**Don't** click **Refresh** once you're recording — it blanks the chart for a second or two.

*Verified run for reference: projected peak 4474ms ±1108, measured peak 48ms, 90s breach avoided,
4427ms peak shaved, confidence 71%. **Use your own numbers.***

---

### [1:04 – 1:32] · runs 28s (24s speech + two 2s pauses) · The loop, acting live

**Say this**

> Now watch it work. It forecasts the breach behind a confidence guard, so it won't act on jitter. It
> names the root hop from real trace data and hands you the exemplar trace. It picks a reversible
> action — scale, because the signal is load; a slow dependency would be circuit-broken instead. Then
> it asks SigNoz whether the breach was actually avoided. Confirmed. And cooldown hands the capacity
> back. *(60 words · 24s)*

**Do this**

1. Scroll so the **Demo** button row *and* the **Closed loop** box are both on screen. You want the
   click and what it causes in the same shot.
2. Say *"Now watch it work."* Click **Inject rising load**.
3. Click **Run ChronoLens** (the dark filled button). Scroll down two notches so the stage pills and
   the status pill are readable — it flips from `idle` to `running`.
4. **Take your hand off the mouse.** Don't hover the log area; it hijacks the scroll.
5. Read the rest of the paragraph *against the pills as they light up*: LEARN → FORECAST → CASCADE →
   DECIDE → ACT → VERIFY → COOLDOWN. Pace yourself to the pills, not to your reading speed.
6. **Stop talking for ~2 seconds when CASCADE lights.** It prints the root hop and a trace ID — let
   that land in silence.
7. **Stop talking for ~2 seconds when VERIFY lights.** Wait for the status pill to settle before you
   say *"Confirmed."*
8. On the last sentence, scroll up so the **Capacity returned** number is in frame — it now shows a
   dollar value.

**Don't** click **Run baseline (no fix)** or **Reset**. Baseline re-runs everything and costs you 40
seconds you don't have.

---

### [1:32 – 1:48] · runs 16s · Blast radius

**A minute before you record**, open a terminal **in the `chronolens/` folder** and run:

```powershell
.\scripts\fault.ps1 dependency
```

That's it — leave it. It sets `dependency-slow` at level 40 and prints what it set. Clear it later
with `.\scripts\fault.ps1 off`.

This fault specifically matters: with the traffic ramp instead, the *entry* service is what's
degrading, so there's nothing upstream to cascade to and you'll get a single victim.

**Say this**

> One service breaching is a symptom. ChronoLens reads SigNoz's own dependency map and forecasts the
> order of failure: payments-db is the root, payments follows, then the storefront, each inheriting
> latency from the tier below. That topology is SigNoz's, derived from traces — not hardcoded.
> *(40 words · 16s)*

**Do this**

1. Scroll down until the box titled **Blast radius** is on screen. It sits next to **Closed loop**,
   so it's a small scroll, not a tab switch.
2. Say *"One service breaching is a symptom."* Don't click yet.
3. Click **Forecast** in that box. Wait ~2 seconds for the list to fill in.
4. Put the cursor on the **top line** (`chronolens-payments-db`, hop `payment.db_query`) and leave it
   there — say *"ChronoLens reads SigNoz's own dependency map and forecasts the order of failure:
   payments-db is the root…"*
5. Move the cursor down the list one name at a time as you name them — *"payments follows, then the
   storefront, each inheriting latency from the tier below."*
6. Move the cursor onto the small grey tag that reads **`signoz-service-map`** and leave it there —
   say *"that topology is SigNoz's, derived from traces, not hardcoded."* This tag is the whole point
   of the beat.
7. Stop. Beat over.

**Bad take, don't use it:** if step 3 shows only one name, or the words
`topology_source: unavailable`, the fault is wrong or the service map hasn't refreshed yet. Wait 30
seconds, click **Forecast** again.

---

### [1:48 – 2:04] · runs 16s · Agent Watch

**Say this**

> Agents fail in ways an HTTP status code never captures, so the same loop watches an LLM agent.
> Caught: sixteen calls to `get_menu`, no progress, sixteen steps against a six-step ceiling. And this
> badge is the point — that verdict came from reading the agent's GenAI spans out of SigNoz, and the
> quality judge reads full answers out of SigNoz logs. *(40 words · 16s)*

**Do this**

1. Before this beat: leave the agent in **normal** mode, so the flip is visible on camera.
2. Scroll so the whole **Agent Watch** box is on screen — the `normal` / `drift` / `loop` buttons at
   the top and the three tiles below.
3. Click **loop**. Say the first sentence while it runs: *"Agents fail in ways an HTTP status code
   never captures, so the same loop watches an LLM agent."* The breaker needs about 10 seconds of
   looping turns before it has anything to read, so don't rush to step 4.
4. Click **Check** on the **Loop / cost breaker** tile.
5. Point at the numbers as you say them: *"sixteen calls to get_menu, no progress, sixteen steps
   against a six-step ceiling."*
6. Move the cursor onto the **`signoz`** badge and leave it there for the last sentence: *"that
   verdict came from reading the agent's GenAI spans out of SigNoz, and the quality judge reads full
   answers out of SigNoz logs."*

**If the badge says `agent-driven`** instead of `signoz`, the logs are cold. Either say so out loud
rather than glossing over it, or wait a minute for the agent to run and re-check.

**Don't** click **Grade** — it's slower and the paragraph already covers it.

---

### [2:04 – 2:30] · runs 26s (22s speech + ~4s letting the card and the rewrite land) · Approve-to-act (Slack)

**Say this**

> This is a live system, so the trust ladder can hold it back: suggest, earn, or auto. Here it's
> suggesting — and this is the part I like. It's three in the morning, you're not at your laptop, no
> VPN, no dashboard. The forecast, the fix and the rollback come to you, and one tap approves it. You
> get an answer instantly, then the verified outcome once SigNoz confirms p99 is back under the SLO.
> *(55 words · 22s)*

**Do this**

1. Before this take: set `CHRONOLENS_AUTONOMY=suggest` in `.env`, **restart Mission Control**, start
   the Slack listener, and full-screen Slack on the ChronoLens channel. This is a separate take from
   the loop beat — you'll splice them.
2. On Mission Control, click **Inject rising load**, then **Run ChronoLens**. Say *"This is a live
   system, so the trust ladder can hold it back: suggest, earn, or auto."*
3. The stage stream stops at **GOVERN** and the status pill shows it's waiting on a human instead of
   acting. Point at that for a second — say *"here it's suggesting."*
4. Cut to **Slack**. The approval card has arrived. Hold it for ~3 seconds so a viewer can actually
   read it, and say the story line: *"It's three in the morning, you're not at your laptop, no VPN, no
   dashboard. The forecast, the fix and the rollback come to you…"*
5. Click **✅ Approve** — say *"…and one tap approves it."*
6. The card is instantly replaced with "⏳ Applying `scale_out` on chronolens-store (approved by
   @you)…". Stay on it — say *"you get an answer instantly."*
7. Wait. The **same message rewrites itself again** with the outcome: applied, SigNoz confirms p99
   back under the SLO, breach avoided, rollback available. Say *"then the verified outcome once SigNoz
   confirms p99 is back under the SLO."* Don't cut away before this rewrite — it's the payoff.
8. Cut back to Mission Control and point at the newest row in the **Prevention ledger**. The receipt
   names the approver, so the decision is auditable afterwards.

**Don't** switch to any other messaging app. One card, one tap, one channel.

---

### [2:30 – 2:44] · runs 14s · SigNoz depth — it writes back

**Say this**

> None of this was clicked together by hand. ChronoLens filed this GenAI dashboard, a cost threshold,
> and this anomaly rule against a learned baseline — already firing, because that cost spike was still
> inside budget but abnormal for this hour. *(35 words · 14s)*

**Do this**

1. Switch to **tab 4** (SigNoz **Dashboards**), with the dashboard list already on screen. Say *"None
   of this was clicked together by hand."*
2. Click **ChronoLens Agent Watch - chronolens-agent**. Five panels render. Say *"ChronoLens filed
   this GenAI dashboard, a cost threshold…"* while pointing at **Tool calls by name** — those grouped
   bars are the loop you triggered earlier.
3. Switch to **tab 5** (SigNoz **Alerts**). Point at the row starting **`ChronoLens anomaly -`**,
   specifically the state column reading **`firing`**, and hold there for the last sentence: *"…and
   this anomaly rule against a learned baseline, already firing, because that cost spike was still
   inside budget but abnormal for this hour."*

That `firing` row is the strongest frame in the beat — SigNoz's own UI confirming a rule ChronoLens
wrote through MCP.

**Don't** open a panel's edit view or the Query Builder. It looks like you're building it live, which
undercuts the whole "auto-filed" claim.

---

## Act 4 · Learning and growth

### [2:44 – 2:55] · runs 11s · Close

**Say this**

> The hard part wasn't predicting anything — it was proving a prevented outage without inventing the
> curve. That's why every field says measured or projected. One command brings the whole stack up
> through Foundry. Thanks for watching. *(28 words · 11s)*

**Do this**

1. Switch back to **tab 1** and scroll to the very top, so the frame matches your cold open — same
   header, same four chips, except **Breach avoided**, **Incidents prevented** and **Capacity
   returned** now hold real numbers.
2. Read the paragraph. Don't move the mouse.
3. Hold the frame for ~1 second after "thanks for watching" before you stop the recording, so the
   video doesn't end on your cursor travelling to the stop button.

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
