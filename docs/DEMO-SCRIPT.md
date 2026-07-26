# ChronoLens — demo video script

**Target length: 2:50** (the hackathon caps at 3:00 — leave yourself a margin).
Every number in the narration below is one this build actually produced. Re-run the demo
before recording and **substitute your own live numbers** rather than reading these.

- [Before you hit record](#before-you-hit-record)
- [The script](#the-script)
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

**Also do this:**
- Start the Slack listener in a spare terminal: `python -m chronolens.cli slack`
- Set `CHRONOLENS_AUTONOMY=suggest` in `.env` **only** if you're demoing the approval card;
  leave it `auto` for the autonomous run.
- Open five tabs in this order: Mission Control (`:8095`), SigNoz Services, SigNoz Traces,
  SigNoz Dashboards, SigNoz Alerts. Pre-open the **Agent Watch** dashboard once so it's warm,
  then go back to the dashboard list. Set every SigNoz time picker to **Last 30 minutes**.
- Blast radius needs the dependency fault, not the ramp. Fire
  `curl -X POST "http://localhost:8090/admin/fault?mode=dependency-slow&level=40"` about a minute
  before you reach that beat, and turn it off (`mode=off&level=0`) when you're done.
- Zoom the browser to **125%** — judges watch on laptops.
- Close Slack notifications from other channels. Silence your phone except WhatsApp if
  you're showing that card.

**Recording:** 1080p minimum, capture system audio off, mic only. Speak ~15% slower than
feels natural.

---

## The script

Each beat below has the **stage direction** first, then the **narration as one paragraph** you
can read straight through. Read the paragraph; the direction tells you what to be doing while
you read it.

The directions are deliberately literal — window, scroll position, which element the cursor
touches, and when. Where a timestamp appears, it's the moment inside the beat, not the clock.

**Tab order, set up before you record** (left to right in one Chrome window):
`1` Mission Control `localhost:8095` · `2` SigNoz **Services** · `3` SigNoz **Traces** ·
`4` SigNoz **Dashboards** · `5` SigNoz **Alerts**. Slack is a separate window on your second
monitor (or `Alt+Tab` position 2 if you're on one screen).

---

### [0:00 – 0:18] Cold open

**On screen**

- **Window:** Chrome, tab 1 (Mission Control), 125% zoom, **scrolled fully to top** so the
  header and the four KPI chips are the only things in frame.
- **Before you start talking:** hard-refresh once (`Ctrl+Shift+R`) so the KPI values animate in
  from `—` rather than sitting there pre-filled. Wait for the header's **SigNoz** pill to turn
  green — if it's grey, SigNoz isn't reachable and nothing below will populate.
- **What must be visible:** the logo + "Predictive SRE · SigNoz closed loop" on the left; the
  three header pills on the right (`SigNoz`, `MODE auto`, `SLO 500ms`); the two solid gradient
  chips (**Breach avoided**, **Incidents prevented**) and the two light cards (**Live p99**,
  **Capacity returned**).
- **Cursor:** parked off to the side, still. No hovering, no scrolling, no clicking for the whole
  18 seconds. The screen is a held frame — you're talking over it.
- **0:14:** begin a slow scroll down so the Chrono-Proof card is entering frame as you say
  "the hard part". Land the scroll before you stop talking.
- **Don't:** read the KPI numbers out loud, name the panels, or say the word "dashboard" yet.
  The claim comes first, the UI tour never happens.

Every reliability tool on the market tells you an outage happened. ChronoLens tells you one was about to — it takes a reversible action to stop it, and then proves from your own telemetry that it never landed. It's a closed loop built entirely on SigNoz, and I want to start with the hard part.

---

### [0:18 – 0:50] Chrono-Proof — proving a negative

**On screen**

- **Window:** still tab 1. Scroll so the **Chrono-Proof — the outage that never happened** card
  fills the frame: title, the measured/projected legend line, the chart, and the five stats
  underneath (**Measured peak · Projected peak · Breach avoided · Peak shaved · Confidence**) all
  visible at once. If the stats are cut off, scroll two more notches — the stats are the payoff.
- **Check the source pill** at the top-right of the card before you talk. It should read
  `signoz`. If it reads anything else, click **Refresh** and wait for it.
- **0:00 – 0:10:** frame held, cursor still, while you set up the problem ("when it works,
  nothing happens").
- **0:10:** move the cursor to the **solid blue line** on the left half of the chart and trace it
  slowly left-to-right as you say "measured".
- **0:16:** lift to the **amber dashed line** and trace it up and to the right as you say
  "projected". Let the shaded confidence band be visible around it — don't cover it with the
  pointer.
- **0:22:** hover and **hold** on the point where the two lines separate. Keep it there ~3
  seconds so the navy tooltip renders and the viewer can read both series values at the same
  timestamp. Don't jiggle — the tooltip flickers.
- **0:26:** drop straight down to the **Breach avoided** stat and rest the cursor beside the
  number as you say "ninety seconds", then slide one stat right to **Peak shaved** for "four and
  a half seconds".
- **0:30:** slide to **Confidence**, then let the cursor sit at the note line under the stats as
  you say the closing sentence about labelling.
- **Don't:** click anything in this beat. A stray click on **Refresh** rebuilds the proof mid-shot
  and the chart will blank for a second or two.

Here's the problem with prevention: when it works, nothing happens. There's no outage to point at. The usual answer is to draw you a nice "what would have happened" curve out of a formula — we had one of those, and we deleted it. This is the honest version instead. The solid blue line is measured: real p99 read out of SigNoz. The dashed amber line is projected — we fit the trend on the samples from before we acted and extrapolate it forward with a confidence band. It's a log scale so you can see both at once. The gap between those two lines is what the fix bought you: ninety seconds of SLO breach avoided, and four and a half seconds shaved off the peak. And every field on this chart is labelled measured or projected, because we never pass an estimate off as a measurement.

*Verified run for reference: projected peak 4474ms ±1108, measured peak 48ms, 90s breach avoided, 4427ms peak shaved, confidence 71%. **Use your own numbers.***

---

### [0:50 – 1:22] The loop, acting live

**On screen**

- **Window:** tab 1. Scroll up briefly to the **Demo** button row, then settle so the row *and*
  the **Closed loop** card (stage pills + live log) are both in frame. You want the click and its
  consequence in the same shot — don't cut between them.
- **0:00:** click **Inject rising load**. The button flashes its busy state; the header
  `MODE` pill stays `auto`.
- **0:02:** click **Run ChronoLens** (the filled navy button). Immediately scroll down two notches
  so the **Closed loop** card is centred and the `loop-state` pill top-right is readable — it
  flips from `idle` to `running`.
- **Then stop touching the mouse.** The rest of this beat is the app performing. Cursor parked to
  the side of the card, not over the log (hovering the log can scroll-hijack).
- **Read against the stage pills as they light:** LEARN → FORECAST → CASCADE → DECIDE → ACT →
  VERIFY → COOLDOWN. Your paragraph is written in that order, so pace yourself to the pills
  rather than to your own reading speed.
- **Pause on CASCADE:** when the CASCADE line lands in the log it prints the root hop and an
  exemplar trace ID. Stop talking for ~2 seconds and let the viewer see the trace ID appear.
  **Optional (costs ~6s):** copy that trace ID, jump to tab 3 (SigNoz Traces), paste, and show
  the real waterfall — only do this if you're under time, it's the single most convincing cut in
  the video.
- **Pause on VERIFY:** stop again when the VERIFY line prints. Let `loop-state` settle to its
  final value (`prevented` / `breach avoided`) before you resume with the p99 number.
- **0:30:** as you say "gives the capacity back", scroll up so the **Capacity returned** KPI chip
  is in frame — it should now show a dollar value instead of `—`.
- **Don't:** click **Run baseline (no fix)** or **Reset** in this beat. Baseline re-runs the whole
  thing without a fix and will eat 40 seconds you don't have.

Now watch it work. I'll inject a load ramp and run the loop. First it reads its own past incidents and pre-provisions capacity from what it learned last time. Then it forecasts the breach — p99 climbing at about eight milliseconds a second — behind a confidence guard, so it won't act on jitter. This next part is my favourite: it names the root hop from real trace data, payment dot charge, and hands you the exemplar trace ID, so it fixes the cause rather than the service that's shouting loudest. It picks a reversible action — scale, because the signal is load; a slow dependency would get circuit-broken, a bad deploy would get rolled back. Then it verifies: it asks SigNoz whether the breach was actually avoided, and p99 is back to fifty-three milliseconds. Confirmed. Cooldown then gives the capacity back — three dollars ninety returned — so prevention isn't paid for with permanent over-provisioning. And if that verification had failed, it would have rolled itself back and escalated to a human.

---

### [1:22 – 1:48] Blast radius

**On screen**

- **Window:** tab 1, scrolled so the **Blast radius** card ("who falls next, and when") occupies
  the right half of the frame. It sits beside **Closed loop**, so a small scroll from the previous
  beat is all you need — no jump.
- **Before this beat:** the fault must be `dependency-slow`, not the traffic ramp, or the deepest
  tier won't be the cause and you'll get one victim. Run
  `curl -X POST "http://localhost:8090/admin/fault?mode=dependency-slow&level=40"` about 60
  seconds before you record this beat, and leave it running through the beat.
- **0:00:** talk over the still card ("one service breaching is a symptom") — don't click yet.
- **0:05:** click **Forecast**. The root line under the header repaints first, then the victim
  rows fill in below it.
- **0:09:** point at the **root line** — it should name `chronolens-payments-db` and the hop
  `payment.db_query`. Rest the cursor there while you say "payments-db is the root".
- **0:14:** walk the cursor down the victim rows in order — `chronolens-payments`, then
  `chronolens-store` — one row per name as you say it, so the ordering is visibly the app's, not
  your narration's.
- **0:20:** move to the **`signoz-service-map`** tag and leave the cursor on it for the last two
  sentences. This tag is the whole point of the beat; it should be on screen and pointed at when
  you say "we didn't hardcode it".
- **If it shows 1 victim or `topology_source: unavailable`:** stop, don't record. The fault isn't
  the dependency one, or the service map hasn't refreshed yet. Wait 30s and click **Forecast**
  again.

One service breaching is a symptom. The real question is what goes down with it. ChronoLens reads SigNoz's own service dependency map and forecasts the order of failure. Payments-db is the root — it's the deepest thing that's actually degrading. Payments follows, then the storefront, each one inheriting latency from the tier below it. And notice this tag: signoz-service-map. That topology is SigNoz's, derived from traces — we didn't hardcode it. If your SigNoz build doesn't expose that endpoint, it says unavailable rather than inventing edges.

---

### [1:48 – 2:20] Agent Watch

**On screen**

- **Window:** tab 1, scrolled so the whole **Agent Watch** card is in frame — the header row with
  the `normal` / `drift` / `loop` mode buttons, and all three tiles below (**Behaviour drift**,
  **Loop / cost breaker**, **Answer quality**).
- **Before this beat:** `CHRONOLENS_AUTONOMY=suggest` in `.env` (otherwise it breaks the loop
  itself and no Slack card appears), and the Slack listener running in a spare terminal
  (`python -m chronolens.cli slack`). Leave the agent in `normal` mode so the mode flip is visible
  on camera.
- **0:00:** click **loop** in the card header. The `a-mode` pill flips to `loop`. Then **wait ~10
  seconds** while you deliver the opening sentences — the agent needs a few looping turns in
  SigNoz before the breaker has anything to read.
- **0:12:** click **Check** on the **Loop / cost breaker** tile. The verdict text replaces the
  placeholder line.
- **0:16:** point at the numbers in that verdict as you say them — the repeated tool
  (`get_menu`), the repeat share, and steps-against-ceiling (`16 / 6`).
- **0:22:** move to the **`signoz`** badge in that verdict line and hold there for the whole
  "that verdict came from reading GenAI spans" sentence. If the badge reads `agent-driven`
  instead, the logs are cold — say so out loud rather than glossing it, or re-record after the
  agent has run another minute.
- **0:28:** switch to the **Slack window**. Full-screen it (or at least crop out other channels)
  so only the ChronoLens approval card is on screen — the Block Kit card with the agent verdict
  and the **Break** / **Deny** buttons.
- **0:32:** click **Break**. Stay on Slack for ~3 seconds and let the message **rewrite itself**
  with the outcome — that in-place edit is the proof the loop closed, and it's easy to miss if you
  cut away too fast.
- **0:38:** cut back to tab 1 for the WhatsApp sentence. No click needed.
- **Don't:** click **Grade** on Answer quality in this beat. It's a slower call and the quality
  verdict is already covered by the narration.

This is an AI-agent observability track, so the same loop watches an LLM agent — and agents fail in ways an HTTP status code never captures. I'll push this one into a loop. Caught: it called get_menu sixteen times, a hundred percent of the turn, making no progress — sixteen steps against a six-step ceiling. The important part is this badge, signoz. That verdict came from reading the agent's GenAI spans out of SigNoz, not from poking the agent. Drift reads traces, the loop breaker reads traces, and the quality judge reads the full answers out of SigNoz logs — because span attributes only carry a truncated preview, and you can't grade what you can't read. And since this is a reversible action on a live system, it asks first. There's the approval card in Slack. I tap Break, it pins the agent back to its last-good baseline, verifies the next turn, and rewrites the message with the outcome. Same contract over WhatsApp if you're away from your desk.

---

### [2:20 – 2:42] SigNoz depth — it writes back

**On screen**

- **Before you record:** open tab 4 (SigNoz **Dashboards**) and pre-open
  **ChronoLens Agent Watch - chronolens-agent** so the five panels are already rendered and warm.
  Set the time picker to **Last 30 minutes**. Then navigate back to the dashboard *list* — you want
  the click into the dashboard on camera, but not the loading spinner.
- **0:00:** switch to tab 4. The list is on screen; the ChronoLens dashboards are visible in it as
  you say "nothing you're looking at here was clicked together by hand".
- **0:03:** click **ChronoLens Agent Watch - chronolens-agent**. Five panels render: cost per
  turn, steps per turn, output tokens, tool calls by name, turn latency p99.
- **0:08 – 0:18:** point at each panel as you name it, in the order the narration names them.
  Linger on **Tool calls by name** — the grouped-by-`tool.name` bars are where the loop you just
  triggered is visible. Then point at **Turn latency p99** for the "deliberately flat" line.
- **0:20:** switch to tab 5 (SigNoz **Alerts**). Both ChronoLens rules should be listed.
- **0:23:** point at the row whose name starts **`ChronoLens anomaly -`** and specifically at its
  state column showing **`firing`**. Hold there for the "learned daily baseline" sentence — this is
  the strongest single frame in the beat, because it's SigNoz's own UI confirming a rule ChronoLens
  wrote via MCP.
- **0:28:** for the "reads and writes" closing sentences, either stay on the Alerts list, or (if
  you have the seconds) cut back to tab 1 and scroll to the **SigNoz surface used** card, which
  lists guard alerts written / firing / channels / webhook events / MCP tools available as live
  counters. That card is the audit trail for everything you just claimed.
- **Optional, only if you're under 2:45:** the **Ask SigNoz — MCP co-pilot** card sits directly
  below. Click the **are any alerts firing?** chip and let the tool-call list render under the
  answer — it shows the actual `tools/call` name. Add one line: "and the same MCP server answers
  questions in plain English — every tool call shown."
- **Don't:** open a panel's edit view or the Query Builder. It looks like you're building it live,
  which undercuts the "auto-filed" claim.

ChronoLens doesn't just read SigNoz, it writes back — and nothing you're looking at here was clicked together by hand. It auto-filed this GenAI dashboard: cost per turn, steps against the ceiling, output tokens, tool mix — and latency, deliberately, so you can watch it stay flat while the behaviour underneath drifts. It filed a threshold alert on cost. And this one is an anomaly rule against a learned daily baseline; it's already firing, because it noticed the cost spike from the loop I just ran. A fixed threshold would have missed that entirely — the cost was still inside budget, just abnormal for this hour. Reads go through Query Builder v5: traces, logs, metrics, the service map. Writes are alerts, dashboards, saved views and silences. It even silences its own alert while it's remediating, so nobody gets paged for a fix that's already in flight.

---

### [2:42 – 2:50] Close

**On screen**

- **0:00:** switch back to tab 1 and scroll to the very top so the frame matches the cold open —
  header plus the four KPI chips. The symmetry is deliberate: same frame, but now **Breach
  avoided**, **Incidents prevented** and **Capacity returned** all hold real numbers instead of
  `—`.
- **Cursor:** still. No clicks, no hovers. Hold this frame through the last sentence and for ~1
  second after "thanks for watching" before you stop the recording — don't let the video end on
  your mouse moving toward the stop button.
- **Optional:** if you'd rather end on reproducibility than on the KPIs, hold a split with
  `casting.yaml` open in the editor on one side. Only do this if it doesn't push you past 3:00.

One command brings the whole stack up through Foundry, and casting.yaml is committed, so you can reproduce exactly what you just saw. That's ChronoLens: it predicts the breach, takes a reversible action, and proves with measured telemetry that the outage never happened. Thanks for watching.

---

## Shot list at a glance

| Time | Screen | Action | The one thing to land |
|---|---|---|---|
| 0:00 | Mission Control | idle | "prevention, not postmortems" |
| 0:18 | Chrono-Proof chart | hover crossover | measured vs projected, labelled |
| 0:50 | Controls → loop stream | Inject, Run | reversible action + SigNoz-verified |
| 1:22 | Blast radius | Forecast | root cause from SigNoz's service map |
| 1:48 | Agent Watch + Slack | loop → Check → Break | `data_source: signoz` + human approval |
| 2:20 | SigNoz UI | dashboards, alerts | it *writes* to SigNoz; anomaly firing |
| 2:42 | Mission Control | — | one-command reproducible |

---

## If something goes wrong on camera

| Problem | Say this, keep moving |
|---|---|
| Loop returns `pre-empted` / no breach | "It pre-provisioned from what it learned, so there's nothing to prevent — that's LEARN working." Reset capacity (`/admin/lever?action=scale&value=-4`) and re-inject. |
| Chrono-Proof shows `prevented=False` | Don't hide it: "the fault is still running, so p99 climbed again — it won't claim a save it can't measure." Turn the fault off, wait, refresh. |
| Slack card doesn't arrive | Check the listener terminal is alive. Fall back to the CLI: `python -m chronolens.cli slack test`. |
| Blast radius shows 1 victim | The *entry* service is degrading, so there's nothing upstream. Use `mode=dependency-slow&level=40` to make the deepest tier the cause. |
| A panel reads `—` | "SigNoz is still filling that window." Move on; don't debug on camera. |

---

## Alternate 60-second cut

If you need a short version, keep only: the Chrono-Proof chart (measured vs projected, the
breach-seconds-avoided number), one full loop run ending on VERIFY, and the auto-created SigNoz
dashboard with the firing anomaly alert. Drop blast radius and WhatsApp.

---

## Don't forget

- **Declare AI-assistant usage in your submission.** Non-disclosure is disqualification.
- Say **"SigNoz"** out loud early and often — "Best Use of SigNoz" is a scored criterion.
- Mention **Foundry + `casting.yaml`** at least once; reproducibility is a hard rule.
- Don't claim the AWS stack is deployed. It's a labelled scaffold.
