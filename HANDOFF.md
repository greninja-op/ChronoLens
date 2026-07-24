# ChronoLens — Project Handoff (read me first)

> You are an AI coding agent picking up an in-progress project. This file tells you
> everything you need: what it is, where the code lives, how to run it, what's done,
> what's next, and which files to focus on vs ignore. Read this fully before acting.

---

## 1. What the project is

**ChronoLens** — a **self-preventing reliability loop** for AI-native systems, built for the
**"Agents of SigNoz"** hackathon (Track 01: AI & Agent Observability). It:

1. **Predicts** an SLO breach (or an AI-agent failure) from live SigNoz telemetry,
2. Takes a **reversible action** to stop it before it lands,
3. **Verifies via SigNoz** that it actually worked (else rolls back),
4. Files a **receipt** — "the outage that never happened."

It also has **Agent Watch**: behavior-drift detection, a loop / cost-spiral breaker, and a
quality judge for a demo LLM agent. It is deeply SigNoz/OpenTelemetry-native (reads via Query
Builder, writes alerts/dashboards/silences/saved-views, emits its own OTel spans + metrics).

---

## 2. Where things live + how to push (IMPORTANT)

- **Workspace root:** `c:\my files in athuls lap\projects\PLANNING\` — this is NOT a git repo,
  just a container of clones and loose files.
- **The project + planning git repo:** `PROJECT-PLANNING/`  →  remote `origin` =
  `github.com/greninja-op/PROJECT-PLANNING-.git`  (the superset; everything is committed here).
- **ChronoLens** lives at `PROJECT-PLANNING/chronolens/` and is a **git subtree** mirrored to its
  own repo: `github.com/greninja-op/ChronoLens.git` (remote name `chronolens`, prefix `chronolens/`).
- **FORESIGHT** (an earlier build) lives at `PROJECT-PLANNING/foresight/`, also a subtree →
  `github.com/greninja-op/foresight.git` (remote `foresight`, prefix `foresight/`).

### How to commit + push
Run the dual-push helper **from the `PROJECT-PLANNING` folder**:
```powershell
./scripts/push.ps1 -m "your commit message"
```
It commits, pushes to `origin`, and — if `chronolens/` or `foresight/` changed — also
`git subtree push`es those to their own repos. (Windows note: git prints progress to stderr in
red but still succeeds; verify with `git status`.)
If you're not on Windows / can't run the .ps1, do it manually:
```bash
git add -A && git commit -m "msg" && git push origin HEAD
# only if chronolens/ changed:
git subtree push --prefix=chronolens chronolens main
```

---

## 3. Project tree (the parts that matter)

```
PROJECT-PLANNING/                     # git repo (origin)
├── scripts/push.ps1                  # dual-push helper (commit + push + subtree push)
├── chronolens/                       # THE PROJECT (git subtree → ChronoLens.git)
│   ├── app.py                        # Mission Control web UI + API (FastAPI, port 8095)
│   ├── demo_store/store.py           # watched web app: 5 fault types + reversible levers (port 8090)
│   ├── demo_agent/agent.py           # demo LLM agent (café assistant), OTel GenAI spans (port 8091)
│   ├── src/chronolens/
│   │   ├── config.py                 # ALL config (reads .env) — Config.load()
│   │   ├── signoz.py                 # SigNoz client: Query Builder reads, alert/dashboard writes
│   │   ├── loop.py                   # the closed loop: LEARN→FORESEE→CLASSIFY→GOVERN→PREVENT→VERIFY→COOLDOWN→RECORD
│   │   ├── foresee.py cascade.py playbook.py prevent.py verify.py cooldown.py
│   │   ├── learn.py governance.py guardrails.py dollars.py record.py notify.py llm.py
│   │   ├── drift.py loopguard.py judge.py   # Agent Watch analyzers
│   │   ├── slack_bot.py              # ★ Slack two-way approve-to-act (see §5)
│   │   ├── otel_self.py metrics_self.py locking.py adapters.py
│   │   └── cli.py                    # `python -m chronolens.cli <cmd>`
│   ├── static/index.html             # dark control-room UI (Tailwind/Chart.js/Lucide)
│   ├── infra/                        # AWS serverless scaffold (SAM: Lambda+EventBridge+DynamoDB+Bedrock)
│   ├── tests/                        # pytest (unit + property-based)
│   ├── scripts/bringup.sh            # one-command SigNoz + MCP via Foundry
│   ├── casting.yaml (+ .lock)        # reproducible Foundry install (hackathon requirement)
│   ├── requirements.txt requirements-dev.txt pytest.ini
│   ├── .env  (git-ignored)           # SECRETS live here — SigNoz + Slack tokens
│   ├── .env.example                  # template
│   └── ERROR-AND-FIXES.md            # every gotcha already hit + fix — READ IF SOMETHING BREAKS
└── docs/, research/, assets/         # planning docs, research archive, blog drafts
```

---

## 4. How ChronoLens works (mental model)

- **The loop** (`src/chronolens/loop.py`) runs one cycle: read past incidents (LEARN) → forecast the
  worst service's p99 breach (FORESEE, behind a confidence guard) → pick the reversible fix that
  matches the signal (CLASSIFY/playbook: load→scale, dependency→circuit-break, pool→resize,
  memory→restart, errors→rollback) → decide if it may act (GOVERN trust ladder) → act behind
  anti-flap guardrails (PREVENT) → confirm via SigNoz (VERIFY, else rollback) → give capacity back
  (COOLDOWN) → file a receipt (RECORD).
- **Trust ladder** (`governance.py`): `auto` (acts always — demo default), `suggest` (only proposes,
  waits for a human), `earn` (autonomous once it has N verified saves). Set via `CHRONOLENS_AUTONOMY`.
- **Agent Watch**: `drift.py` (behavior fingerprint vs baseline), `loopguard.py` (loop/cost-spiral
  breaker), `judge.py` (answer-quality grading). Driven from `app.py` endpoints `/api/agent/*`.

Run the loop from the CLI (set `PYTHONPATH=src` first):
```powershell
$env:PYTHONPATH="src"
python -m chronolens.cli services      # list services SigNoz sees
python -m chronolens.cli foresee       # forecast the worst service
python -m chronolens.cli respond       # full loop (managed)
python -m chronolens.cli respond off   # baseline arm (predict, no action) — the A/B
python -m chronolens.cli ab            # baseline then managed, back to back
python -m chronolens.cli prevented     # the receipts ledger
python -m chronolens.cli config        # show active config (incl. Slack status)
```

---

## 5. Slack integration (approve-to-act) — what we built and how it works

**What it does:** when GOVERN only *suggests* (autonomy `suggest`, or `earn` before trust), ChronoLens
posts an **interactive Approve/Deny card to Slack**. Tapping **Approve** runs the real
PREVENT→VERIFY→COOLDOWN→RECORD path and edits the message with the SigNoz-verified outcome. There's
also an **Agent Watch card**: on a loop / cost-spiral / drift it posts a **"🛑 Break / pin baseline"**
approval; approving pins the demo agent back to its last-good baseline (reversible) and verifies the
next turn. Uses Slack **Socket Mode** (no public URL needed).

**Key files:**
- `src/chronolens/slack_bot.py` — all of it: message/Block-Kit builders (`build_approval_blocks`,
  `build_agent_approval_blocks`), posting (`post_approval`, `post_agent_approval`, `post_text`),
  execution on click (`execute_approved`, `execute_agent_break`, `record_denial`, `record_agent_ignore`),
  and the Socket Mode listener (`run_listener`) with button handlers.
- `src/chronolens/loop.py` — calls `_maybe_request_approval(...)` in the "suggested" branch.
- `app.py` — `/api/agent/loopcheck` and `/api/agent/drift` post an agent approval when they detect a
  problem and Slack is configured.
- `src/chronolens/config.py` — `slack_bot_token`, `slack_app_token`, `slack_channel`, and
  `Config.slack_enabled()`.
- `tests/test_slack.py` — unit tests for the Block-Kit builders.

**Credentials & channel (already set up):**
- The tokens are stored in **`chronolens/.env`** (git-ignored — DO NOT commit, DO NOT paste them into
  chat or any tracked file):
  - `SLACK_BOT_TOKEN=xoxb-…`  (Bot User OAuth token — posts/reads)
  - `SLACK_APP_TOKEN=xapp-…`  (App-Level token, scope `connections:write` — opens Socket Mode)
  - `SLACK_CHANNEL=C0BKQTT7TL1`  (the channel ID; the bot is already invited to it)
- Slack app: created in workspace, **Blank app**; bot has `chat:write` (+ `channels:history`); the
  bot is a member of the channel above. It does NOT have `channels:read`, so it posts by channel **ID**,
  not name — keep `SLACK_CHANNEL` as the `C…` id.

**Run the Slack flow:**
```powershell
$env:PYTHONPATH="src"
python -m chronolens.cli slack test    # posts a test message to the channel
python -m chronolens.cli slack         # runs the Socket Mode listener (leave running)
```
Then set `CHRONOLENS_AUTONOMY=suggest` in `.env` and run a loop, or hit the agent endpoints, to make
cards appear. Requires `slack_sdk` + `slack_bolt` (in requirements.txt; `pip install -r requirements.txt`).

> Deps note: `slack_sdk` and `slack_bolt` must be installed in the venv. The venv is at
> `chronolens/.venv/` (use `.venv\Scripts\python.exe` on Windows).

---

## 6. Current state — done / in progress / next

**Done & verified:**
- Full closed loop, Agent Watch, Mission Control UI, tests, AWS SAM scaffold, `casting.yaml(.lock)`.
- Verified live against a running SigNoz (breach predicted → reversible action → SigNoz-confirmed).
- **Slack approve-to-act — DONE for both the infra loop AND Agent Watch.** Tested: cards post to the
  channel, the listener runs, clicking a button drives the real path and rewrites the message.

**Where we left off (a live demo was running):**
- The demo agent (`:8091`) was started in **loop mode** and the Slack **listener** was running; a real
  agent-loop card was posted to the channel for a click-through demo. Those were local background
  processes and will have stopped when the IDE/terminals closed — just restart them (see §5 and §4).

**Next up (highest value first):**
1. **Make Agent Watch read from SigNoz (the one honest gap).** Today `loopcheck`/`drift` call the
   agent's `/chat` directly. Change them to query the agent's GenAI spans **from SigNoz** (the
   `agent.turn` spans carry `gen_ai.usage.*`, `llm.step_count`, `llm.cost_usd`, `agent.tools`,
   `agent.looping`). This makes "deep SigNoz usage" true across the whole product. Extend `signoz.py`
   as needed.
2. Prove the whole thing end-to-end live (SigNoz + demo store + agent + Slack listener), fix any wiring.
3. Wire the loopcheck/drift/quality + agent-mode controls into Mission Control UI buttons (click-driven demo).
4. (Optional) Real Bedrock LLM mode for EXPLAIN + the demo agent; make the SAM scaffold a real deploy.

---

## 7. Which files to focus on vs ignore

**Focus on:** everything under `PROJECT-PLANNING/chronolens/` (that's the project). For planning
context, `PROJECT-PLANNING/docs/` and `PROJECT-PLANNING/research/` are useful but not code.

**Ignore / don't touch:**
- The workspace-root reference clones — `signoz/`, `graphify/`, `DesignSoul/`, `agent-skills/`,
  `gigapipe/`, and `refs/`. They're reference material, not our code.
- `graphify-out/` (a generated knowledge graph — not part of the project).
- Anything under `.kiro/` — that's Kiro-editor-specific config. If you are **not** Kiro, ignore it
  entirely; it has no bearing on the project code.
- Never commit `chronolens/.env` (secrets). It's git-ignored — keep it that way.

---

## 8. If you are NOT Kiro (connecting a different editor)

- This is a normal **Python** project. Environment: Windows, Python 3.9+; a virtualenv exists at
  `chronolens/.venv/`. Always set `PYTHONPATH=src` when running (`chronolens` package lives under `src/`).
- Install deps: `pip install -r chronolens/requirements.txt` (and `requirements-dev.txt` for tests).
- Run tests from `chronolens/`: `python -m pytest -q`.
- There is no build step; it's run directly (FastAPI apps + a CLI).
- Prerequisites for a full live run: Docker + WSL2 for SigNoz (brought up via Foundry
  `chronolens/scripts/bringup.sh`), then the demo store, the agent, `app.py`, and the Slack listener.
- Ports: SigNoz UI `:8080`, OTLP `:4317/:4318`, SigNoz MCP `:8000/mcp`, demo store `:8090`,
  demo agent `:8091`, Mission Control `:8095`.
- Config is entirely env-driven via `chronolens/.env` (see `.env.example` for every key).

---

## 9. TL;DR for the agent
Work inside `PROJECT-PLANNING/chronolens/`. Commit via `PROJECT-PLANNING/scripts/push.ps1 -m "…"`.
Secrets (SigNoz + Slack tokens) are in `chronolens/.env` — never commit them. Slack approve-to-act is
built and working (listener: `python -m chronolens.cli slack`). The next meaningful task is making
Agent Watch detect from SigNoz spans instead of calling the agent directly. Read `ERROR-AND-FIXES.md`
before debugging environment issues.
