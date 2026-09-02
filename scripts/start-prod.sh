#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/compose.sh -f docker-compose.prod.yml up -d --build
./scripts/compose.sh -f docker-compose.prod.yml ps
