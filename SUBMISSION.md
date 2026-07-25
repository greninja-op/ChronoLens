# 🏆 Agents of SigNoz — Hackathon Submission

**Hackathon**: Agents of SigNoz · $20,000 in prizes  
**Duration**: July 20 – July 26, 2026  
**Submission Form**: https://forms.gle/AgentsOfSigNoz (Google Form)

---

## 📋 Submission Form Fields

> Only **one person** from the team needs to fill the form.

| Field | Value |
|-------|-------|
| **Email** | *(your email)* |
| **Team name** | *(write YOUR NAME if participating SOLO)* |
| **Name of person submitting** | *(your name)* |
| **Track** | ☑️ Track 1: AI & Agent Observability |
| **Project description** | *(see below)* |
| **GitHub link to project** | https://github.com/greninja-op/ChronoLens *(must include casting.yaml & casting.yaml.lock)* |
| **Deployed link to project** | https://chronolens.reticule.dev *(or your deployment URL)* |
| **YouTube video demo link** | *(≤ 3 min: About project · Tech stack · Demo · Learning)* |
| **How you used SigNoz** | *(see below)* |
| **Project blog link** | *(NEW blog, not from pre-blogging challenge)* |
| **Hackathon experience** | *(your reflection)* |

---

## 📝 Submission Content

### Track Selection
> ☑️ **Track 1: AI & Agent Observability**  
> ChronoLens directly targets AI agent observability with SigNoz GenAI spans, LLM cost tracking, and agent drift detection via the Agent Watch circuit breaker.

---

### Project Description

ChronoLens is a Predictive SRE Control Plane that uses SigNoz as its 
observability backbone. It forecasts P99 latency SLO breaches before they 
happen, fires WhatsApp approve-to-act cards to on-call engineers, and 
executes reversible closed-loop remediations — all verified back against 
SigNoz metrics.

Key capabilities:
- Predictive breach forecasting (linear regression on SigNoz P99 telemetry)
- WhatsApp interactive approval cards with HMAC-signed webhook callbacks
- Closed-loop SRE: PREVENT → VERIFY → COOLDOWN → RECORD
- Agent Watch: SigNoz GenAI spans monitoring for LLM cost drift + circuit breaker
- Sarvam AI multilingual alerts (Hindi/English voice + text)
- Prevention Ledger: tracks incidents prevented and cost saved
- Live mission control dashboard at localhost:8095

---

### How We Used SigNoz

SigNoz is the core observability engine powering every layer of ChronoLens:

1. **P99 Latency Telemetry** — ChronoLens queries SigNoz's metrics API in real-time
   to fetch per-service P99 latency. A linear regression model runs on the 
   slope to forecast when the SLO wall (500ms) will be breached.

2. **GenAI Spans (Agent Watch)** — We ingest SigNoz's OpenTelemetry GenAI spans 
   to monitor LLM token usage, cost per request, and model drift. When cost 
   spikes 3x above baseline, the Agent Watch circuit breaker fires a WhatsApp 
   alert with Break/Ignore buttons.

3. **Verification Loop** — After every remediation (scale_out, rollback, etc.), 
   ChronoLens re-queries SigNoz to verify the P99 latency returned below the 
   SLO threshold before marking an incident as "prevented."

4. **SigNoz as Source of Truth** — All SRE decisions (approve, deny, cooldown) 
   are grounded in live SigNoz data, not synthetic metrics. The dashboard 
   shows real-time SigNoz data in the cascade topology and agent watch panels.

5. **Two-Way Channels** — SigNoz alerts feed into WhatsApp and Sarvam AI voice 
   calls, making it a complete human-in-the-loop observability system.

---

## ✅ Pre-submission Checklist

- [ ] `casting.yaml` present in repo root
- [ ] `casting.yaml.lock` present in repo root
- [ ] GitHub repo is **public**: https://github.com/greninja-op/ChronoLens
- [ ] YouTube demo video recorded (≤ 3 min)
  - [ ] About the project
  - [ ] Tech stack and architecture
  - [ ] Live demo if possible
  - [ ] Learning and growth (optional)
- [ ] Blog post written (NEW, not from pre-blogging challenge)
- [ ] SigNoz usage is clearly documented in README
- [ ] Deployed project link is live and accessible
- [ ] Form submitted before **July 26, 2026 deadline**

---

## 🛠️ Tech Stack (for blog/video)

| Layer | Technology |
|-------|-----------|
| Observability | SigNoz (P99 metrics, GenAI spans, OTel) |
| Forecasting | Linear regression on SigNoz telemetry |
| Alerts | WhatsApp Business Cloud API (Meta) |
| Webhook | FastAPI `/webhook/whatsapp` + HMAC-SHA256 |
| Voice/Translate | Sarvam AI (Saarika STT, Bulbul TTS) |
| LLM Engine | Azure AI (gpt-5.4-mini / gpt-5.4-nano) |
| Dashboard | FastAPI + Vanilla JS + Chart.js |
| Deployment | Docker + Reticule VPS |

---

## 📌 Important Rules

> **IMPORTANT:** Blogs written in the pre-blogging challenge will **not** be considered valid.  
> Write a **NEW and detailed blog** on your hackathon project and how you used SigNoz.

- Usage of SigNoz is **mandatory**
- A detailed blog post on SigNoz usage is **mandatory**
- You **cannot submit the same project** in all tracks — submit the form again for different tracks
- Judges may re-run Foundry against `casting.yaml` to reproduce your deployment
