#!/usr/bin/env bash
# Gera um trace real no Datadog via POST /chat no gateway local.
# Uso único: ./scripts/generate-trace.sh
# A cada 5 min: ./scripts/install-trace-timer.sh
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8001}"
GATEWAY_URL="${GATEWAY_URL%/}"
LOG="${TRACE_LOG:-/var/log/retail-trace.log}"

MESSAGES=(
  "Status do pedido BR-10482 e estoque do SKU-7781"
  "Qual a política de troca e devolução?"
  "Estoque do SKU-3302"
  "Onde está o pedido BR-22011?"
)

idx=$(( $(date +%s) / 300 % ${#MESSAGES[@]} ))
message="${1:-${MESSAGES[$idx]}}"
payload="$(python3 -c 'import json,sys; print(json.dumps({"message": sys.argv[1]}))' "$message")"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

http_code="$(
  curl -sS -o /tmp/retail-trace-body.json -w "%{http_code}" \
    --connect-timeout 5 --max-time 30 \
    -X POST "${GATEWAY_URL}/chat" \
    -H "Content-Type: application/json" \
    -d "$payload" || echo "000"
)"

line="${ts} http=${http_code} msg=${message}"
if [[ -w "$(dirname "$LOG")" ]] || [[ -w "$LOG" ]]; then
  echo "$line" >> "$LOG" || echo "$line"
else
  echo "$line"
fi

if [[ "$http_code" != "200" ]]; then
  echo "Falha ao gerar trace (http=${http_code}). Gateway em ${GATEWAY_URL}?" >&2
  head -c 300 /tmp/retail-trace-body.json >&2 || true
  echo >&2
  exit 1
fi

echo "$line"
exit 0
