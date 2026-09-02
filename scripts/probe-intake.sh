#!/usr/bin/env bash
# Envia um span mínimo ao intake LLM Observability usando só curl (sem pip).
# Rode na EC2, no diretório do projeto. Não imprime a API key.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "ERRO: .env não encontrado neste diretório." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ -z "${DD_API_KEY:-}" ]]; then
  echo "ERRO: DD_API_KEY vazia no .env" >&2
  exit 1
fi

SITE="${DD_SITE:-us5.datadoghq.com}"
SITE="${SITE#https://}"
SITE="${SITE#http://}"
SITE="${SITE#app.}"
SITE="${SITE#api.}"
SITE="${SITE%/}"
ML_APP="${DD_LLMOBS_ML_APP:-retail-assistant}"
DD_ENV_VAL="${DD_ENV:-aws-ec2}"
URL="https://api.${SITE}/api/intake/llm-obs/v1/trace/spans"

SPAN_ID="$(python3 -c 'import secrets; print(secrets.randbits(64))')"
TRACE_ID="$(python3 -c 'import secrets; print(f"{secrets.randbits(128):032x}")')"
START_NS="$(python3 -c 'import time; print(time.time_ns())')"

PAYLOAD="$(python3 - <<PY
import json
print(json.dumps({
  "data": {
    "type": "span",
    "attributes": {
      "ml_app": "${ML_APP}",
      "session_id": "probe-ec2",
      "tags": ["service:retail-gateway", "env:${DD_ENV_VAL}", "source:probe"],
      "spans": [{
        "name": "retail-customer-chat",
        "span_id": "${SPAN_ID}",
        "trace_id": "${TRACE_ID}",
        "parent_id": "undefined",
        "start_ns": ${START_NS},
        "duration": 5000000.0,
        "status": "ok",
        "service": "retail-gateway",
        "ml_app": "${ML_APP}",
        "session_id": "probe-ec2",
        "meta": {
          "kind": "workflow",
          "input": {"value": "probe from EC2"},
          "output": {"value": "probe ok"}
        }
      }]
    }
  }
}))
PY
)"

TMP_BODY="$(mktemp)"
HTTP_CODE="$(
  curl -sS -o "$TMP_BODY" -w "%{http_code}" \
    --connect-timeout 10 --max-time 20 \
    -X POST "$URL" \
    -H "DD-API-KEY: ${DD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" || echo "000"
)"
BODY="$(head -c 400 "$TMP_BODY" 2>/dev/null || true)"
rm -f "$TMP_BODY"

echo "intake: ${URL}"
echo "ml_app: ${ML_APP}  env: ${DD_ENV_VAL}  key_len: ${#DD_API_KEY}"
echo "http: ${HTTP_CODE}"
echo "body: ${BODY}"

if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "202" ]]; then
  echo "Intake ACEITOU o span. Abra no Datadog US5:"
  echo "  https://app.${SITE}/llm/traces"
  echo "  LLM Observability → Traces → ml_app:${ML_APP}  env:${DD_ENV_VAL}"
  exit 0
fi

echo "Intake NÃO aceitou."
case "$HTTP_CODE" in
  000) echo "Falha de rede/timeout. Libere HTTPS 443 de saída para api.${SITE}" ;;
  403) echo "403: DD_SITE ou DD_API_KEY inválidos para esta org." ;;
  400) echo "400: payload rejeitado." ;;
  *) echo "Veja o body acima." ;;
esac
exit 1
