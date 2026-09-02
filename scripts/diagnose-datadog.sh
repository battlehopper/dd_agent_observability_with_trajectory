#!/usr/bin/env bash
# Diagnóstico: por que o agente não aparece no Datadog LLM Observability.
# Rode na EC2, no diretório do projeto (ex. ~/llmagent ou /opt/llmagent).
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(./scripts/compose.sh)
if [[ -f docker-compose.prod.yml ]]; then
  COMPOSE+=(-f docker-compose.prod.yml)
fi

echo "=== 1. .env no host (valores mascarados) ==="
if [[ ! -f .env ]]; then
  echo "ERRO: .env não existe. cp deploy/.env.ec2.example .env e preencha DD_API_KEY / DD_SITE"
  exit 1
fi
python3 - <<'PY'
from pathlib import Path
for line in Path(".env").read_text().splitlines():
    s=line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k,v=s.split("=",1)
    v=v.strip().strip('"').strip("'")
    if "KEY" in k.upper() or "SECRET" in k.upper():
        print(f"{k}={'set('+str(len(v))+' chars)' if v else 'EMPTY'}")
    else:
        print(f"{k}={v}")
PY

echo
echo "=== 2. Variáveis DENTRO do container gateway ==="
"${COMPOSE[@]}" exec -T gateway sh -c 'echo DD_API_KEY_LEN=${#DD_API_KEY}; echo DD_SITE=$DD_SITE; echo DD_ENV=$DD_ENV; echo DD_LLMOBS_ML_APP=$DD_LLMOBS_ML_APP; echo TRAJECTORY_EXPORT=$TRAJECTORY_EXPORT'

echo
echo "=== 3. GET /health ==="
curl -sS http://127.0.0.1:8001/health || true
echo

echo
echo "=== 4. POST /chat (dispara export) ==="
curl -sS -X POST http://127.0.0.1:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Status do pedido BR-10482 e estoque do SKU-7781"}' || true
echo

echo
echo "=== 5. Logs recentes do gateway ==="
"${COMPOSE[@]}" logs --tail=40 gateway || true

echo
echo "Onde olhar no Datadog (NÃO é APM Services):"
echo "  LLM Observability / Agent Observability → aplicação retail-assistant"
echo "  Site tem que bater com DD_SITE (US5 → app.us5.datadoghq.com)"
echo "  Se last_export.reason=missing_api_key: recrie os containers depois de editar .env"
echo "  ./scripts/compose.sh -f docker-compose.prod.yml up -d --build --force-recreate"
