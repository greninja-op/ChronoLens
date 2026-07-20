# ChronoLens — the self-preventing reliability loop

> Predicts a breach from live SigNoz telemetry, takes a **reversible** action to stop it before it lands, verifies via SigNoz that it worked, and files a receipt — the outage that never happened.

Built for the **Agents of SigNoz** hackathon (Track: AI & Agent Observability).

## The loop
```
FORESEE  → watch a service's p99, project the trend to a time-to-breach
PREVENT  → take one reversible action (scale out) before the breach lands
VERIFY   → confirm via SigNoz the breach was actually avoided (else roll back)
RECORD   → file the "incident prevented" receipt so an invisible save is provable
```
Plus **cascade prediction**: ChronoLens reads the service topology and names the *root* hop a failure will spread from, so it fixes the cause, not the symptom. ChronoLens is itself OpenTelemetry-instrumented, so its own loop shows up in SigNoz (full-circle).

## Architecture (local dev)
```
demo store ──OTel──▶ SigNoz + MCP (Foundry)
                          ▲   │
                          │   ▼
                     ChronoLens (this app)
                foresee · prevent · verify · record
                          │
                          ▼
                   Mission Control UI  (http://localhost:8095)
```
Production target is serverless AWS (Bedrock + Lambda + EventBridge + DynamoDB + S3).

## Prerequisites
- **Python 3.9+**
- **Docker** (with Compose v2). On **Windows use WSL2 (Ubuntu)** — Foundry runs on Linux/macOS.
- **Foundry** (`foundryctl`) to bring up SigNoz + its MCP server in one command.

---

## Quickstart

### 1. Bring up SigNoz + MCP (one command, in WSL2/bash)
```bash
bash scripts/bringup.sh
# or drive Foundry directly:  foundryctl cast -f casting.yaml
```
This stands up SigNoz UI (:8080), the OTel collector (:4317/:4318), and the SigNoz MCP server (:8000/mcp).

### 2. Configure ChronoLens
Create an **Admin/Editor API key** in SigNoz (Settings → API Keys), then:
```bash
cp .env.example .env          # fill in SIGNOZ_URL + SIGNOZ_API_KEY
pip install -r requirements.txt
```

### 3. Run it — three terminals

**Windows PowerShell:**
```powershell
# terminal 1 — the demo store (streams OTel traces to SigNoz, admin knobs on :8090)
$env:PYTHONPATH="src"; python -m demo_store.store

# terminal 2 — Mission Control UI on http://localhost:8095
$env:PYTHONPATH="src"; python app.py

# terminal 3 — drive the loop from the CLI (optional; the UI has buttons too)
$env:PYTHONPATH="src"; python -m chronolens.cli services
```

**macOS/Linux/WSL2 (bash):**
```bash
export PYTHONPATH=src
python -m demo_store.store          # terminal 1
python app.py                       # terminal 2
python -m chronolens.cli services   # terminal 3
```

> **Windows note:** always set `PYTHONPATH=src` (the package lives under `src/`). See `ERROR-AND-FIXES.md` for every gotcha we already hit and fixed.

---

## The demo (the money shot: an A/B)

Open **http://localhost:8095**, then:

1. Click **Inject rising load** — the demo store's demand climbs; watch the p99 chart start rising toward the SLO.
2. Click **Run baseline (no fix)** first — ChronoLens forecasts the breach but takes no action → it breaches (the "without me" arm).
3. **Reset to healthy**, inject again, then click **Run ChronoLens** — it predicts, scales out *before* the breach, verifies via SigNoz, and the line never reaches the wall.
4. The **Incidents Prevented** scoreboard ticks up with the receipt.

Same fault, run twice: one breaches, one gets defused. That's the demo.

### From the CLI
```bash
python -m chronolens.cli foresee       # forecast the worst service now
python -m chronolens.cli respond       # full loop (managed): predict → prevent → verify → record
python -m chronolens.cli respond off   # baseline arm: predict + record, no action (A/B)
python -m chronolens.cli prevented     # the receipts ledger
```

---

## SigNoz features used
- **Query Builder v5** — every p99/RED read is a `queryType:"builder"` traces query (`p99(duration_nano)`), the same shape the SigNoz MCP server executes.
- **Services / RED stats** — to pick and score services.
- **Alerts & dashboards** — ChronoLens can create a guarding SigNoz alert + dashboard for a watched service (`create_alert`, `create_dashboard`).
- **MCP-compatible** — reads use the MCP query shape; the SigNoz MCP server ships alongside via `casting.yaml`.
- **Full-circle** — ChronoLens exports its own OTel spans (`chronolens.stage`), so its loop is visible in SigNoz next to the app it protects.

## Layout
```
chronolens/
├── demo_store/store.py        # the watched app: rising-load fault + reversible levers
├── src/chronolens/
│   ├── config.py  signoz.py  otel_self.py
│   ├── foresee.py  prevent.py  verify.py  cascade.py  record.py
│   ├── loop.py    # foresee → prevent → verify → record
│   └── cli.py
├── app.py + static/index.html # Mission Control UI
├── scripts/bringup.sh         # one-command SigNoz + MCP (Foundry)
├── casting.yaml               # committed Foundry install
├── requirements.txt  .env.example
└── ERROR-AND-FIXES.md         # every gotcha + fix (read this if something breaks)
```

## Ports
| Service | URL |
| --- | --- |
| SigNoz UI | http://localhost:8080 |
| SigNoz MCP | http://localhost:8000/mcp (`/livez`) |
| OTLP ingest | localhost:4317 (gRPC) / 4318 (HTTP) |
| Demo store admin | http://localhost:8090/admin/status |
| Mission Control | http://localhost:8095 |
