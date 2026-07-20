#!/usr/bin/env bash
#
# One-command SigNoz + MCP bring-up for ChronoLens (via Foundry).
#
#   bash scripts/bringup.sh
#
# Preflight-checks Docker, deploys the stack from casting.yaml, and waits until
# the SigNoz API (:8080) and MCP server (:8000) report healthy.
#
# Foundry runs on Linux/macOS. On Windows, run this inside WSL2 (Ubuntu).
# See ../docs/14-signoz-install-guide.md for install/troubleshooting.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "==> Preflight: Docker"
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker isn't reachable. Start Docker Desktop (WSL2 integration on) and retry." >&2
  exit 1
fi

echo "==> Preflight: foundryctl"
if ! command -v foundryctl >/dev/null 2>&1; then
  echo "ERROR: foundryctl not found. Install Foundry, then re-run." >&2
  echo "       See ../docs/14-signoz-install-guide.md" >&2
  exit 1
fi

echo "==> Deploying SigNoz + MCP from casting.yaml"
foundryctl cast -f casting.yaml

echo "==> Waiting for SigNoz UI (http://localhost:8080) ..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8080 >/dev/null 2>&1; then echo "    SigNoz UI up."; break; fi
  sleep 3
done

echo "==> Waiting for SigNoz MCP (http://localhost:8000/livez) ..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/livez >/dev/null 2>&1; then echo "    MCP up."; break; fi
  sleep 3
done

cat <<'DONE'

ChronoLens infra is up:
  SigNoz UI          -> http://localhost:8080
  OTLP ingestion     -> localhost:4317 (gRPC) / localhost:4318 (HTTP)
  SigNoz MCP server  -> http://localhost:8000/mcp   (liveness: /livez)

Next:
  1) Create an Admin/Editor API key in SigNoz (Settings -> API Keys)
  2) cp .env.example .env   and fill in SIGNOZ_URL + SIGNOZ_API_KEY
  3) pip install -r requirements.txt
  4) Run the demo store, Mission Control, and the loop (see README.md)
DONE
