#!/usr/bin/env bash
# Local one-command launcher: demo store + Mission Control + a gentle load stream.
# Assumes SigNoz is already up (bash scripts/bringup.sh) and .env has SIGNOZ_API_KEY.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
export PYTHONPATH=src
PY="${PYTHON:-python}"

echo "==> demo store  -> :8090"
$PY -m demo_store.store &          STORE=$!
sleep 3
echo "==> Mission Control -> http://localhost:8095"
$PY app.py &                        APP=$!
sleep 2
echo "==> load generator (gentle)"
$PY scripts/loadgen.py 300 &        LOAD=$!

trap 'kill $STORE $APP $LOAD 2>/dev/null || true' EXIT INT TERM
echo "All up. Open http://localhost:8095  (Ctrl-C to stop)"
wait
