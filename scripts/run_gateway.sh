#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec uvicorn services.gateway.main:app --host "${GATEWAY_HOST:-0.0.0.0}" --port "${GATEWAY_PORT:-8001}"
