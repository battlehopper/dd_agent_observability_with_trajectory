#!/usr/bin/env bash
# Gera um trace real no Datadog via POST /chat no gateway local.
# Uso único: ./scripts/generate-trace.sh
# A cada 5 min: ./scripts/install-trace-timer.sh
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8001}"
GATEWAY_URL="${GATEWAY_URL%/}"
LOG="${TRACE_LOG:-/var/log/retail-trace.log}"
WAIT_SECS="${GATEWAY_WAIT_SECS:-60}"

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
body="$(mktemp /tmp/retail-trace-body.XXXXXX.json)"

cleanup() { rm -f "$body"; }
trap cleanup EXIT

wait_gateway() {
  local i
  for i in $(seq 1 "$WAIT_SECS"); do
    if curl -sf --connect-timeout 2 --max-time 3 "${GATEWAY_URL}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

log_line() {
  local line="$1"
  if mkdir -p "$(dirname "$LOG")" 2>/dev/null && ( [[ -w "$LOG" ]] || [[ -w "$(dirname "$LOG")" ]] ); then
    echo "$line" >> "$LOG" || echo "$line"
  else
    echo "$line"
  fi
}

if ! wait_gateway; then
  line="${ts} http=000 msg=${message} error=gateway_not_ready ${GATEWAY_URL}/health"
  log_line "$line"
  echo "Gateway não respondeu em ${WAIT_SECS}s (${GATEWAY_URL}/health)." >&2
  echo "Espere os containers subirem: docker compose -f docker-compose.prod.yml ps" >&2
  exit 1
fi

set +e
http_code="$(
  curl -sS -o "$body" -w "%{http_code}" \
    --connect-timeout 5 --max-time 30 \
    -X POST "${GATEWAY_URL}/chat" \
    -H "Content-Type: application/json" \
    -d "$payload"
)"
curl_rc=$?
set -e

if [[ "$curl_rc" -ne 0 || -z "$http_code" ]]; then
  http_code="000"
fi

line="${ts} http=${http_code} msg=${message}"
log_line "$line"

if [[ "$http_code" != "200" ]]; then
  echo "Falha ao gerar trace (http=${http_code} curl_rc=${curl_rc}). Gateway: ${GATEWAY_URL}" >&2
  if [[ -s "$body" ]]; then
    head -c 300 "$body" >&2
    echo >&2
  fi
  exit 1
fi

echo "$line"
exit 0
