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

Each beat below has the **stage direction** first, then the **narration as one paragraph** you
can read straight through. Read the paragraph; the direction tells you what to be doing while
you read it.

---

### [0:00 – 0:18] Cold open

**On screen:** Mission Control, KPI row filling in. Don't narrate the UI yet.

Every reliability tool on the market tells you an outage happened. ChronoLens tells you one was about to — it takes a reversible action to stop it, and then proves from your own telemetry that it never landed. It's a closed loop built entirely on SigNoz, and I want to start with the hard part.

---

### [0:18 – 0:50] Chrono-Proof — proving a negative

**On screen:** Scroll to the Chrono-Proof chart. Hover the crossover point so the tooltip shows.
Point at the "breach avoided" number when you say it.

Here's the problem with prevention: when it works, nothing happens. There's no outage to point at. The usual answer is to draw you a nice "what would have happened" curve out of a formula — we had one of those, and we deleted it. This is the honest version instead. The solid blue line is measured: real p99 read out of SigNoz. The dashed amber line is projected — we fit the trend on the samples from before we acted and extrapolate it forward with a confidence band. It's a log scale so you can see both at once. The gap between those two lines is what the fix bought you: ninety seconds of SLO breach avoided, and four and a half seconds shaved off the peak. And every field on this chart is labelled measured or projected, because we never pass an estimate off as a measurement.

*Verified run for reference: projected peak 4474ms ±1108, measured peak 48ms, 90s breach avoided, 4427ms peak shaved, confidence 71%. **Use your own numbers.***

---

### [0:50 – 1:22] The loop, acting live

**On screen:** Click **Inject rising load**, then **Run ChronoLens**. Let the stage pills light up.
Pause your reading when CASCADE appears, and again on VERIFY — let those two land on their own.

Now watch it work. I'll inject a load ramp and run the loop. First it reads its own past incidents and pre-provisions capacity from what it learned last time. Then it forecasts the breach — p99 climbing at about eight milliseconds a second — behind a confidence guard, so it won't act on jitter. This next part is my favourite: it names the root hop from real trace data, payment dot charge, and hands you the exemplar trace ID, so it fixes the cause rather than the service that's shouting loudest. It picks a reversible action — scale, because the signal is load; a slow dependency would get circuit-broken, a bad deploy would get rolled back. Then it verifies: it asks SigNoz whether the breach was actually avoided, and p99 is back to fifty-three milliseconds. Confirmed. Cooldown then gives the capacity back — three dollars ninety returned — so prevention isn't paid for with permanent over-provisioning. And if that verification had failed, it would have rolled itself back and escalated to a human.

---

### [1:22 – 1:48] Blast radius

**On screen:** Click **Forecast** in the Blast radius panel. Point at the `signoz-service-map` tag.

One service breaching is a symptom. The real question is what goes down with it. ChronoLens reads SigNoz's own service dependency map and forecasts the order of failure. Payments-db is the root — it's the deepest thing that's actually degrading. Payments follows, then the storefront, each one inheriting latency from the tier below it. And notice this tag: signoz-service-map. That topology is SigNoz's, derived from traces — we didn't hardcode it. If your SigNoz build doesn't expose that endpoint, it says unavailable rather than inventing edges.

---

### [1:48 – 2:20] Agent Watch

**On screen:** Agent Watch panel. Click **loop**, then **Check** on the loop breaker. Point at the
`signoz` badge. Cut to Slack as the card arrives, then tap **Break**.

This is an AI-agent observability track, so the same loop watches an LLM agent — and agents fail in ways an HTTP status code never captures. I'll push this one into a loop. Caught: it called get_menu sixteen times, a hundred percent of the turn, making no progress — sixteen steps against a six-step ceiling. The important part is this badge, signoz. That verdict came from reading the agent's GenAI spans out of SigNoz, not from poking the agent. Drift reads traces, the loop breaker reads traces, and the quality judge reads the full answers out of SigNoz logs — because span attributes only carry a truncated preview, and you can't grade what you can't read. And since this is a reversible action on a live system, it asks first. There's the approval card in Slack. I tap Break, it pins the agent back to its last-good baseline, verifies the next turn, and rewrites the message with the outcome. Same contract over WhatsApp if you're away from your desk.

---

### [2:20 – 2:42] SigNoz depth — it writes back

**On screen:** SigNoz tab → Dashboards → the auto-created **Agent Watch** dashboard → then Alerts,
showing the anomaly rule in `firing` state.

ChronoLens doesn't just read SigNoz, it writes back — and nothing you're looking at here was clicked together by hand. It auto-filed this GenAI dashboard: cost per turn, steps against the ceiling, output tokens, tool mix — and latency, deliberately, so you can watch it stay flat while the behaviour underneath drifts. It filed a threshold alert on cost. And this one is an anomaly rule against a learned daily baseline; it's already firing, because it noticed the cost spike from the loop I just ran. A fixed threshold would have missed that entirely — the cost was still inside budget, just abnormal for this hour. Reads go through Query Builder v5: traces, logs, metrics, the service map. Writes are alerts, dashboards, saved views and silences. It even silences its own alert while it's remediating, so nobody gets paged for a fix that's already in flight.

---

### [2:42 – 2:50] Close

**On screen:** Back to Mission Control, KPI row.

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
