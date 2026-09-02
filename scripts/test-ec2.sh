#!/usr/bin/env bash
# Testes do agente retail a partir da própria EC2 (curl no gateway local).
# Uso:
#   ./scripts/test-ec2.sh
#   GATEWAY_URL=http://127.0.0.1:8001 ./scripts/test-ec2.sh
#   ./scripts/test-ec2.sh "Qual a política de troca?"
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8001}"
GATEWAY_URL="${GATEWAY_URL%/}"

pretty() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin), ensure_ascii=False, indent=2))'
  else
    cat
  fi
}

chat() {
  local message="$1"
  echo
  echo "==> POST /chat  ${message}"
  curl -sS -X POST "${GATEWAY_URL}/chat" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"message": sys.argv[1]}))' "$message" 2>/dev/null || printf '{"message":"%s"}' "$message")" \
    | pretty
}

echo "==> GET  ${GATEWAY_URL}/health"
curl -sS -f "${GATEWAY_URL}/health" | pretty

if [[ $# -gt 0 ]]; then
  chat "$*"
  exit 0
fi

chat "Status do pedido BR-10482 e estoque do SKU-7781"
chat "Qual a política de troca e devolução?"
chat "Estoque do SKU-3302"

echo
echo "OK. No Datadog, filtre ml_app:retail-assistant e env:aws-ec2 (ou o DD_ENV do .env)."
