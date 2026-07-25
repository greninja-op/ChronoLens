# ChronoLens: Building a Predictive SRE Control Plane with SigNoz, WhatsApp Approve-to-Act, and Agent Watch

> **Submitted for the Agents of SigNoz Hackathon 2026 (Track 1: AI & Agent Observability)**

---

## Executive Summary

Traditional Site Reliability Engineering (SRE) is inherently **reactive**. Alerts trigger *after* P99 latency breaches an SLO wall, *after* error rates spike, or *after* customers experience downtime. In microservice architectures and AI agent workflows, this lag costs thousands of dollars per minute in degraded user experience and uncontained infrastructure cascades.

**ChronoLens** transforms SRE from reactive post-mortems into **predictive, closed-loop prevention**. Powered by **SigNoz** as its observability backbone, ChronoLens:

1. **Predicts SLO Breaches Before They Happen**: Uses real-time linear regression on SigNoz P99 latency telemetry to calculate breach slope (`ms/s`) and exact ETA to breach.
2. **Human-in-the-Loop Approve-to-Act via WhatsApp**: Fires interactive WhatsApp cards with `[✅ Approve Fix]` and `[❌ Deny Fix]` buttons directly to on-call engineers.
3. **Closed-Loop Remediation & SigNoz Verification**: Executes automated, reversible actions (`scale_out`, `rollback`, `cache_warm`) and immediately re-queries SigNoz to verify that P99 returned below SLO before closing the incident loop.
4. **Agent Watch (GenAI Spans Observability)**: Monitors OpenTelemetry GenAI spans in SigNoz to detect LLM token cost drift, latency degradation, and context window bloat, triggering an automatic circuit breaker.
5. **Multilingual Bharat Voice Layer**: Integrates Sarvam AI (Saarika STT & Bulbul TTS) to deliver voice and Hindi/English alerts.

---

## 🏛️ System Architecture

ChronoLens connects SigNoz observability with two-way human feedback and automated closed-loop remediation:

```
                  ┌─────────────────────────────────────────┐
                  │          SigNoz Observability           │
                  │   (P99 Metrics API + OTel GenAI Spans)  │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ Real-Time Telemetry Poll
                  ┌─────────────────────────────────────────┐
                  │    ChronoLens Forecasting Engine        │
                  │   (Linear Regression & Slope Analysis)  │
                  └────────────────────┬────────────────────┘
                                       │
                      Breach Forecast Detected (P99 -> SLO)
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │   WhatsApp Business Cloud API (Meta)    │
                  │     Interactive Approve-to-Act Card     │
                  └────────────────────┬────────────────────┘
                                       │
                             Engineer Taps [Approve]
                                       │
                                       ▼ Webhook Callback (HMAC SHA-256)
                  ┌─────────────────────────────────────────┐
                  │       Closed-Loop SRE Engine            │
                  │   PREVENT ──► VERIFY ──► COOLDOWN       │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼ Verification
                  ┌─────────────────────────────────────────┐
                  │      SigNoz Telemetry Re-Query          │
                  │   (Confirms P99 < 500ms SLO Wall)       │
                  └─────────────────────────────────────────┘
```

---

## 🔬 How ChronoLens Uses SigNoz

SigNoz is not an afterthought in ChronoLens — it is the **central nervous system**:

### 1. P99 Latency Telemetry & Predictive Forecasting
ChronoLens polls SigNoz telemetry at high frequency. Instead of waiting for `P99 > 500ms`, our forecasting engine calculates the rate of latency growth ($\frac{d(P99)}{dt}$) over a sliding window:

$$\text{ETA to Breach} = \frac{\text{SLO Wall} - \text{Current P99}}{\text{Slope (ms/s)}}$$

If $P99 = 480\text{ms}$, $\text{SLO} = 500\text{ms}$, and $\text{Slope} = +18.5\text{ms/s}$, ChronoLens forecasts an SLO breach in **18.2 seconds** and triggers proactive remediation before any user experiences a failure.

### 2. GenAI Spans & Agent Watch (Track 1 Focus)
AI agents behave unpredictably: prompt bloat, infinite retry loops, and token cost surges can silently degrade application economics. 

ChronoLens ingests **SigNoz OpenTelemetry GenAI Spans** (`gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`, `gen_ai.client.token.cost`). When token cost drifts **> 3x above baseline** in a 60-second window, the **Agent Watch Circuit Breaker** fires an interactive WhatsApp card permitting the SRE to:
- **Throttle Agent Context Window**: Truncates history to prevent token explosions.
- **Pin Baseline Model**: Reverts from expensive models (e.g. GPT-5.4) back to cost-optimized fallback models (e.g. gpt-5.4-nano).

### 3. Verification Loop
Remediation without verification is dangerous. After executing an action (`scale_out`), ChronoLens queries SigNoz to verify that:
1. P99 latency dropped below the 500ms SLO target.
2. Error rates did not spike.
3. System metrics stabilized.

Only after SigNoz confirms stabilization does ChronoLens mark the incident as **PREVENTED** in the **Prevention Ledger**.

---

## 📱 Interactive Approve-to-Act via WhatsApp

Alert fatigue is real. SREs receive hundreds of unactionable Slack/email pings daily. ChronoLens changes this by making alerts **interactive and actionable**:

1. **Card Delivery**: When a breach is forecasted, ChronoLens posts an interactive WhatsApp card containing:
   - Affected Service & Current P99
   - Predicted ETA to SLO breach
   - Proposed Reversible Remediation Action
   - `[✅ Approve Fix]` and `[❌ Deny Fix]` buttons
2. **HMAC-SHA256 Signed Webhooks**: Button taps send a payload to FastAPI `/webhook/whatsapp`, verified against Meta's `x-hub-signature-256`.
3. **Instant Execution**: Tapping **Approve** executes the fix, verifies via SigNoz, and replies to the WhatsApp thread with the outcome.

---

## 🌐 Mission Control Dashboard

The ChronoLens web dashboard (`http://localhost:8095`) provides complete real-time visibility:
- **Top 4 Scorecards**: Incidents Prevented, Total Cost Saved, Current P99 Latency vs. SLO, and Agent Watch Circuit Status.
- **Dark Emerald P99 Latency Graph**: Live Chart.js visualization comparing actual latency against the predicted slope and 500ms SLO threshold.
- **Vertical Cascade Topology**: Service dependency graph (`/order` → `cart.lookup` → `inventory.check` → `payment.charge` → `payment.db_query`) highlighting root-cause spans.
- **Prevention Ledger**: Real-time log of every prevented incident, action taken, and dollar savings.

---

## 🛠️ Tech Stack

- **Observability**: SigNoz (P99 Telemetry, OTel GenAI Spans, ClickHouse Query API)
- **Backend & Webhook**: Python 3.11, FastAPI, Uvicorn, HMAC-SHA256
- **Predictive Engine**: NumPy, SciPy (Linear Regression Slope Analysis)
- **Messaging**: WhatsApp Business Cloud API (Meta Graph API v23.0)
- **Multilingual / Voice**: Sarvam AI (Saarika STT, Bulbul TTS, Translate API)
- **LLM Engine**: Azure AI Foundry (`gpt-5.4-mini` / `gpt-5.4-nano`)
- **Frontend**: Vanilla JS, Tailwind CSS, Chart.js, Lucide Icons
- **Deployment**: Docker, Docker Compose, Reticule VPS

---

## 💡 What We Learned & Key Takeaways

1. **Predictive > Reactive**: Catching latency trends 15-20 seconds before breach prevents user impact entirely.
2. **SigNoz Telemetry is Surprisingly Rich**: SigNoz's OpenTelemetry integration allowed us to query both standard microservice metrics and GenAI LLM span telemetry out-of-the-box.
3. **Human-in-the-Loop Builds Trust**: Full autonomous remediation can be terrifying for SRE teams. WhatsApp interactive Approve-to-Act balances speed with human governance.

---

## 🔗 Links & Resources

- **GitHub Repository**: [https://github.com/greninja-op/ChronoLens](https://github.com/greninja-op/ChronoLens)
- **Live Demo Dashboard**: `http://localhost:8095`
- **SigNoz Project**: [https://signoz.io](https://signoz.io)
