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
  `5` SigNoz **Alerts**.
- Pre-open the **Agent Watch** dashboard once so it's warm, then go back to the dashboard list.
  Set every SigNoz time picker to **Last 30 minutes**.
- Slack in its own window. WhatsApp in a **third** window — see below.
- Zoom Chrome to **125%**. Judges watch on laptops.
- Your editor open on `casting.yaml` for Act 2, and on the architecture block of `README.md`.

**Approve-to-act prep — we film Slack, not WhatsApp**

Both surfaces run the same approval engine, so filming one is enough. **Slack is the one we
film**, because Socket Mode dials outward: no public URL, no tunnel, nothing to expire mid-take.
WhatsApp gets a single spoken mention and no screen time.

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
- Don't claim WhatsApp is live on camera unless you've re-tested it. The WhatsApp path needs a
  public callback URL for the tap to return, and Meta access tokens expire — ours currently
  returns `401 / code 190`. Saying "the same contract runs over WhatsApp" is accurate; showing a
  card you can't tap is not worth the risk.

**Recording:** 1080p minimum, system audio off, mic only. Speak ~15% slower than feels natural.

---

## Pace check

The narration is written to a budget, because 3:00 is roughly **430 spoken words at 150 wpm** —
and pauses eat into that. Each beat carries its word count. If you find yourself rushing, cut a
whole beat (the cut list is at the bottom); don't speed-read, it reads as panic on camera.

| Act | Window | Words |
|---|---|---|
| 1 · About | 0:00 – 0:18 | 45 |
| 2 · Tech stack + architecture | 0:18 – 0:42 | 60 |
| 3 · Live demo | 0:42 – 2:42 | 300 |
| 4 · Learning | 2:42 – 2:55 | 30 |

Each beat below gives the **stage direction** first — window, scroll position, which element the
cursor touches, and when — then the **narration as one paragraph** you read straight through.
Timestamps inside a direction are moments *within* that beat.

---

## Act 1 · About the project

### [0:00 – 0:18] The claim

**On screen**

- **Window:** tab 1 (Mission Control), 125% zoom, **scrolled fully to top** so the header and the
  four KPI chips are the only things in frame.
- **Before you talk:** hard-refresh (`Ctrl+Shift+R`) so the KPIs animate in from `—` instead of
  sitting there pre-filled. Wait for the header **SigNoz** pill to go green; if it's grey, SigNoz
  is unreachable and nothing below will populate.
- **In frame:** logo + "Predictive SRE · SigNoz closed loop"; the pills `SigNoz`, `MODE auto`,
  `SLO 500ms`; the two gradient chips (**Breach avoided**, **Incidents prevented**) and the two
  light cards (**Live p99**, **Capacity returned**).
- **Cursor:** parked off to the side, completely still, for all 18 seconds. This is a held frame.
- **Don't:** read the KPIs out loud, name the panels, or say "dashboard". The claim comes first;
  the UI tour never happens.

> Every reliability tool tells you an outage happened. ChronoLens tells you one was about to — it
> takes a reversible action to stop it, and then proves from your own telemetry that it never
> landed. It's a closed loop, built entirely on SigNoz, and it watches both your infrastructure
> and your AI agents. *(45 words)*

---

## Act 2 · Tech stack and architecture

### [0:18 – 0:42] How it's wired

**On screen**

- **0:00:** cut to your editor showing the **architecture block in `README.md`** — the
  `demo store ──OTel──▶ SigNoz + MCP (Foundry)` diagram. Full-screen the editor; no file tree, no
  terminal.
- **0:06:** trace the arrows with the cursor as you name them: store → OTel → SigNoz, then SigNoz
  → ChronoLens, then ChronoLens back into SigNoz. The *back into* arrow is the one that matters —
  linger there.
- **0:14:** switch to `casting.yaml` in the same editor window. Scroll once so it's obviously a
  real manifest, not a stub.
- **0:20:** cut back to tab 1 so Act 3 opens on Mission Control.
- **Don't:** open a terminal and run anything here. Act 2 is 24 seconds; a `docker compose` scroll
  will eat all of it.

> Everything is OpenTelemetry. A three-service demo store and an LLM agent export traces, metrics
> and logs to SigNoz. ChronoLens reads them back through Query Builder v5 and the MCP server, and
> writes back — dashboards, alerts, saved views, silences. It's Python and FastAPI, it's itself
> instrumented, so its own loop shows up in SigNoz. SigNoz and its MCP server come up through
> Foundry from this committed `casting.yaml`. *(60 words)*

---

## Act 3 · Live demo

### [0:42 – 1:08] Chrono-Proof — proving a negative

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

> Here's the problem with prevention: when it works, nothing happens. The solid blue line is
> measured — real p99 from SigNoz. The amber dashed line is projected: we fit the trend on the
> samples from before we acted and extrapolate with a confidence band. Log scale, so you see both.
> The gap is what the fix bought: ninety seconds of breach avoided, four and a half seconds off
> the peak. Every field is labelled measured or projected. *(70 words)*

*Verified run for reference: projected peak 4474ms ±1108, measured peak 48ms, 90s breach avoided,
4427ms peak shaved, confidence 71%. **Use your own numbers.***

---

### [1:08 – 1:36] The loop, acting live

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
- **0:24:** scroll up so **Capacity returned** is in frame — it now holds a dollar value.
- **Don't:** click **Run baseline (no fix)** or **Reset**. Baseline re-runs the whole thing and
  costs you 40 seconds.

> Now watch it work. It forecasts the breach — p99 climbing eight milliseconds a second — behind a
> confidence guard, so it won't act on jitter. It names the root hop from real trace data,
> `payment.charge`, and hands you the exemplar trace. It picks a reversible action: scale, because
> the signal is load; a slow dependency would be circuit-broken, a bad deploy rolled back. Then it
> asks SigNoz whether the breach was actually avoided — p99 back to fifty-three milliseconds,
> confirmed — and cooldown hands the capacity back. *(80 words)*

---

### [1:36 – 1:52] Blast radius

**On screen**

- **Window:** tab 1, scrolled so the **Blast radius** card ("who falls next, and when") holds the
  right half of the frame. It sits beside **Closed loop**, so this is a small scroll, not a jump.
- **Before this beat:** the fault must be the dependency one or you'll get a single victim. Fire
  `curl -X POST "http://localhost:8090/admin/fault?mode=dependency-slow&level=40"` about a minute
  earlier and leave it running.
- **0:03:** click **Forecast**. The root line repaints, then the victim rows fill in.
- **0:06:** point at the **root line** — `chronolens-payments-db`, hop `payment.db_query` — and
  hold there.
- **0:09:** walk down the victim rows in order, one per name: `chronolens-payments`, then
  `chronolens-store`.
- **0:13:** move to the **`signoz-service-map`** tag and stay there for the last sentence.
- **If it shows 1 victim or `topology_source: unavailable`:** don't record. Wrong fault, or the
  service map hasn't refreshed. Wait 30s, click **Forecast** again.

> One service breaching is a symptom. ChronoLens reads SigNoz's own service dependency map and
> forecasts the order of failure: payments-db is the root, payments follows, then the storefront,
> each inheriting latency from the tier below. And that topology is SigNoz's, derived from traces —
> we didn't hardcode it. *(45 words)*

---

### [1:52 – 2:10] Agent Watch

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
> Caught: sixteen calls to `get_menu`, no progress, sixteen steps against a six-step ceiling. And
> this badge matters — that verdict came from reading the agent's GenAI spans out of SigNoz. Drift
> and the breaker read traces; the quality judge reads full answers out of SigNoz logs, because
> spans only carry a truncated preview. *(60 words)*

---

### [2:10 – 2:32] Approve-to-act (Slack)

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
  names who approved it and which surface it came from.
- **Don't:** put WhatsApp on screen. It's one line of narration, not a shot. See the prep note.

> Reversible or not, this is a live system, so the trust ladder can hold it back: suggest, earn, or
> auto. Here it's suggesting, and this is the part I like. It's three in the morning, you're not at
> your laptop, no VPN, no dashboard open. The forecast, the action and the rollback come to you, and
> one tap approves it. You get an answer immediately, then the verified outcome once SigNoz confirms
> p99 is back under the SLO. Same engine answers on WhatsApp for whoever's actually on call — and the
> ledger records which surface approved it. *(90 words)*

---

### [2:32 – 2:42] SigNoz depth — it writes back

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

> None of this was clicked together by hand. ChronoLens filed this GenAI dashboard, a cost
> threshold, and this anomaly rule against a learned baseline — already firing, because the cost
> spike from that loop was still inside budget but abnormal for this hour. *(45 words)*

---

## Act 4 · Learning and growth

### [2:42 – 2:55] Close

**On screen**

- **0:00:** back to tab 1, scrolled to the very top so the frame matches the cold open — same
  header, same four KPI chips, except **Breach avoided**, **Incidents prevented** and **Capacity
  returned** now hold real numbers instead of `—`.
- **Cursor:** still. Hold the frame through the last sentence and for ~1 second after, so the
  video doesn't end on your mouse travelling to the stop button.

> The hard part wasn't predicting anything — it was proving a prevented outage without inventing
> the curve. That's why every field on that chart says measured or projected. One command brings
> the whole stack up through Foundry. Thanks for watching. *(40 words)*

---

## Shot list at a glance

| Time | Act | Screen | Action | The one thing to land |
|---|---|---|---|---|
| 0:00 | 1 | Mission Control, top | held frame | prevention, not postmortems |
| 0:18 | 2 | editor: README + `casting.yaml` | trace the arrows | OTel in, SigNoz out, writes back |
| 0:42 | 3 | Chrono-Proof card | hover the crossover | measured vs projected, labelled |
| 1:08 | 3 | Demo row → Closed loop | Inject, Run | reversible action, SigNoz-verified |
| 1:36 | 3 | Blast radius | Forecast | root cause from SigNoz's service map |
| 1:52 | 3 | Agent Watch | loop → Check | `data_source: signoz` |
| 2:10 | 3 | Slack (full screen) | one tap Approve | 3am, no laptop, one tap → instant ack → verified |
| 2:32 | 3 | SigNoz Dashboards → Alerts | click through | it *writes*; anomaly `firing` |
| 2:42 | 4 | Mission Control, top | held frame | proving a negative, honestly |

---

## If something goes wrong on camera

| Problem | Say this, keep moving |
|---|---|
| Loop returns `pre-empted` / no breach | "It pre-provisioned from what it learned, so there's nothing to prevent — that's LEARN working." Reset capacity (`/admin/lever?action=scale&value=-4`) and re-inject. |
| Chrono-Proof shows `prevented=False` | Don't hide it: "the fault is still running, so p99 climbed again — it won't claim a save it can't measure." Turn the fault off, wait, refresh. |
| Slack card doesn't arrive | Check the listener terminal is alive, then `python -m chronolens.cli slack test`. |
| Tapping Approve does nothing | The listener died. Restart `python -m chronolens.cli slack` — the card stays valid, the button carries its whole payload. |
| Approve sits on "⏳ Applying…" | Verification is still running (it can take tens of seconds). Wait for the second rewrite; don't tap anything else. |
| A judge asks about WhatsApp | "Same engine, second door — it's in the repo and documented, we filmed Slack because it needs no public callback URL." Don't demo it live. |
| Loop acts instead of asking | You're still in `auto`. Set `CHRONOLENS_AUTONOMY=suggest` **and restart** Mission Control. |
| Blast radius shows 1 victim | Wrong fault. `mode=dependency-slow&level=40`, wait, Forecast again. |
| Agent verdict badge says `agent-driven` | Logs are cold. Say it out loud, or wait a minute and re-check. |
| A panel reads `—` | "SigNoz is still filling that window." Move on; don't debug on camera. |

---

## Alternate 60-second cut

Keep only: the Chrono-Proof chart (measured vs projected, breach-seconds avoided), one full loop
run ending on VERIFY, the Slack one-tap approval, and the auto-created SigNoz dashboard with the
firing anomaly alert. Drop Act 2, blast radius and Agent Watch.

**If the full cut runs long, drop in this order:** blast radius (1:36) → the `casting.yaml` half
of Act 2 → Agent Watch (1:52). Never drop Chrono-Proof, the approval tap, or the SigNoz writes —
those are the three scored moments.

---

## Don't forget

- **Declare AI-assistant usage in your submission.** Non-disclosure is disqualification.
- The four acts must stay in the form's order: About → Tech stack → Demo → Learning.
- Say **"SigNoz"** out loud early and often — "Best Use of SigNoz" is a scored criterion.
- Mention **Foundry + `casting.yaml`** at least once; reproducibility is a hard rule.
- Don't claim the AWS stack is deployed. It's a labelled scaffold.
