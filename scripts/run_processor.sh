#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec uvicorn services.processor.main:app --host "${PROCESSOR_HOST:-0.0.0.0}" --port "${PROCESSOR_PORT:-8002}"
