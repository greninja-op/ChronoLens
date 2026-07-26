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
  SigNoz Dashboards, SigNoz Alerts.
- Zoom the browser to **125%** — judges watch on laptops.
- Close Slack notifications from other channels. Silence your phone except WhatsApp if
  you're showing that card.

**Recording:** 1080p minimum, capture system audio off, mic only. Speak ~15% slower than
feels natural.

---

## The script

### [0:00 – 0:18] Cold open — the problem

> **VISUAL:** Mission Control, KPI row filling in. Don't narrate the UI yet.

> "Every reliability tool on the market tells you an outage *happened*.
>
> ChronoLens tells you one was *about to*, does something reversible about it, and then
> proves — from your own telemetry — that it never landed.
>
> It's a closed loop built entirely on SigNoz. Let me show you the hard part first."

---

### [0:18 – 0:50] The hard part — proving a negative

> **VISUAL:** Scroll to the Chrono-Proof chart. Hover the crossover point so the tooltip shows.

> "This is the problem with prevention: when it works, *nothing happens*. There's no outage
> to point at. Most tools solve that by drawing you a pretty 'what would have happened' curve
> from a formula. We had one of those. We deleted it.
>
> Here's the honest version. The **solid blue line is measured** — real p99 read out of SigNoz.
> The **dashed amber line is projected**: we fit the trend on the samples from *before* we acted,
> and extrapolate it forward with a confidence band. Log scale, so you can see both at once.
>
> The gap between them is what the fix bought you. **[POINT]** Ninety seconds of SLO breach
> avoided. Four-and-a-half seconds of peak latency shaved off. And every field on this chart is
> labelled *measured* or *projected* — we never pass an estimate off as a measurement."

*Numbers from a verified run: projected peak 4474ms ±1108, measured peak 48ms, 90s breach
avoided, 4427ms peak shaved, confidence 71%.*

---

### [0:50 – 1:22] The loop — watch it act

> **VISUAL:** Click **Inject rising load**, then **Run ChronoLens**. Let the stage pills light
> up live. Do not talk over the whole stream — pause and let one or two lines land.

> "Now watch it work. I'll inject a load ramp and run the loop.
>
> It reads past incidents and **pre-provisions** capacity from what it learned last time.
> It forecasts the breach — p99 climbing at eight milliseconds a second — behind a confidence
> guard, so it won't act on jitter.
>
> **[PAUSE on CASCADE]** This is the bit I like: it names the root hop from real trace data —
> `payment.charge` — and gives you the exemplar trace ID. So it fixes the *cause*, not the
> service that's shouting loudest.
>
> It picks a **reversible** action — scale, because the signal is load. A slow dependency would
> get circuit-broken; a bad deploy would get rolled back.
>
> Then **VERIFY**: it asks SigNoz whether the breach was actually avoided. p99 back to
> fifty-three milliseconds. Confirmed. And **COOLDOWN** gives the capacity back — three dollars
> ninety returned, so prevention isn't paid for with permanent over-provisioning.
>
> If verification had failed, it would have rolled itself back and escalated."

---

### [1:22 – 1:48] Blast radius — who falls next

> **VISUAL:** Click **Forecast** in the Blast radius panel.

> "One service breaching is a symptom. The real question is what goes down *with* it.
>
> ChronoLens reads **SigNoz's own service dependency map** and forecasts the order.
> `payments-db` is the root — it's the deepest thing that's actually degrading.
> `payments` follows, then the storefront, each inheriting latency from the tier below.
>
> Note the tag: `signoz-service-map`. That topology is SigNoz's, derived from traces — we
> didn't hardcode it. And if your SigNoz build doesn't expose that endpoint, it says
> `unavailable` rather than inventing edges."

---

### [1:48 – 2:20] Agent Watch — Track 01

> **VISUAL:** Agent Watch panel. Click **loop**, then **Check** on the loop breaker. Point at
> the `signoz` badge. Cut to the Slack card arriving.

> "This is an AI-agent observability track, so the same loop watches an LLM agent — and agents
> fail in ways an HTTP status code never captures.
>
> I'll push the agent into a loop. **[CLICK]** Caught: `get_menu` called sixteen times, a
> hundred percent of the turn, no progress. Sixteen steps against a six-step ceiling.
>
> The important part is this badge — **`signoz`**. That verdict came from reading the agent's
> GenAI spans *out of SigNoz*, not from poking the agent. Drift reads traces. The loop breaker
> reads traces. The quality judge reads the full answers out of SigNoz **logs**, because span
> attributes only carry a truncated preview — and you can't grade what you can't read.
>
> And because it's a *reversible* action on a live system, it asks. **[SLACK]** There's the
> approval card. I tap **Break**, it pins the agent back to its last-good baseline, verifies the
> next turn, and rewrites the message with the outcome. Same contract on WhatsApp if you're
> away from your desk."

---

### [2:20 – 2:42] SigNoz depth — it writes back

> **VISUAL:** SigNoz tab → Dashboards → the auto-created **Agent Watch** dashboard → Alerts,
> showing the anomaly rule **firing**.

> "ChronoLens doesn't just read SigNoz — it writes back, and nothing here was clicked together
> by hand.
>
> It auto-filed this **GenAI dashboard**: cost per turn, steps against the ceiling, tokens,
> tool mix — plus latency, deliberately, to show it staying flat while behaviour drifts.
>
> It filed a threshold alert on cost. And this one is an **anomaly** rule on a learned daily
> baseline — it's already firing, because it noticed the cost spike from that loop I just ran.
> A fixed threshold would have missed it: the cost was still inside budget, just abnormal for
> this hour.
>
> Reads go through Query Builder v5 — traces, logs, metrics, the service map. Writes are alerts,
> dashboards, saved views and silences. And it silences its own alert while remediating, so
> nobody gets paged for a fix already in flight."

---

### [2:42 – 2:50] Close

> **VISUAL:** Back to Mission Control, KPI row.

> "One command brings the whole stack up through Foundry — `casting.yaml` is committed, so you
> can reproduce exactly what you just saw.
>
> ChronoLens: it predicts the breach, takes a reversible action, and proves with measured
> telemetry that the outage never happened. Thanks for watching."

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
