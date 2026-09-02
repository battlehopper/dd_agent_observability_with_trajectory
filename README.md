# LLM Multi-Agent Retail — Trajectory + Datadog LLM Observability

Exemplo de ecossistema retail com dois agentes LLM em microserviços distintos, instrumentados com **Trajectory** (sem `dd-trace`). Cada serviço continua identificável (`retail-gateway` / `retail-processor`), mas compartilham `DD_LLMOBS_ML_APP=retail-assistant` e o mesmo `trace_id` para aparecerem como **um único fluxo** no LLM Observability.

O plano detalhado está em [INSTRUMENTATION.md](INSTRUMENTATION.md).

## Arquitetura

| Componente | `service` (tag Trajectory) | Papel |
| --- | --- | --- |
| Gateway | `retail-gateway` | Agente 1 — recebe o usuário, resume intenção, delega |
| Processor | `retail-processor` | Agente 2 — consulta contexto retail (mock ERP) e responde |

Ambos exportam spans via **API HTTP** de LLM Observability (`/api/intake/llm-obs/v1/trace/spans`), o mesmo transporte que o [datadog-labs/trajectory](https://github.com/datadog-labs/trajectory) usa — **não** há `ddtrace`, `ddtrace-run` nem `LLMObs.enable()`.

```
usuário → POST /chat (gateway :8001)
            workflow retail-customer-chat
              agent retail-concierge
                task enrich-user-intent
                  llm concierge-inference
                tool delegate-to-specialist  ──headers Trajectory──▶  POST /process (processor :8002)
                                                                       workflow retail-backoffice-process
                                                                         agent retail-specialist
                                                                           retrieval retail-knowledge-base
                                                                           llm specialist-inference
```

## Pré-requisitos

- Python 3.10+
- Conta Datadog com LLM Observability habilitada (export opcional)
- `DD_API_KEY` e `DD_SITE` do seu tenant (ex.: `us5.datadoghq.com`)

## Execução local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edite .env com DD_API_KEY e DD_SITE (pode deixar a chave vazia para só captura local)
set -a && source .env && set +a
```

Terminal 1 — especialista (porta 8002):

```bash
./scripts/run_processor.sh
```

Terminal 2 — concierge (porta 8001):

```bash
./scripts/run_gateway.sh
```

Terminal 3 — demo:

```bash
python scripts/demo_client.py
```

Cenário sugerido:

```bash
python scripts/demo_client.py --message "Status do pedido BR-10482 e estoque do SKU-7781"
```

Perguntas sobre pedidos, estoque e políticas de troca disparam o fluxo completo entre os dois agentes.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
python scripts/demo_client.py
```

Produção (só o gateway público na 8001):

```bash
cp deploy/.env.ec2.example .env
./scripts/start-prod.sh
```

## O que observar no Datadog

| Variável | Onde ver |
| --- | --- |
| `DD_SITE` | Canto inferior esquerdo (ex. US5 → `us5.datadoghq.com`) |
| `DD_LLMOBS_ML_APP` | Nome da app em LLM Observability / Agent Observability |

Se `DD_SITE` estiver errado (ex. `datadoghq.com` numa org US5), o intake retorna API Key invalid (403) e nenhum trace aparece.

### LLM Observability (visão unificada)

Acesse **LLM Observability → `retail-assistant`**. Um trace de `/chat` deve mostrar:

- `workflow` — `retail-customer-chat` (gateway)
- `agent` — `retail-concierge`
- `task` — `enrich-user-intent`
- `llm` — inferência do concierge
- `tool` — `delegate-to-specialist`
- `workflow` — `retail-backoffice-process` (processor, mesmo `trace_id`)
- `agent` — `retail-specialist`
- `retrieval` — `retail-knowledge-base`
- `llm` — inferência do especialista

Tags Trajectory em todo span: `trajectory.version`, `trajectory.session_id`, `trajectory.trace_type:turn`, `trajectory.client_source:retail-multiagent`.

### Captura local (sem Datadog)

Mesmo sem `DD_API_KEY`, o SDK grava:

- `.trajectory/sessions/session-<id>.jsonl` — eventos de sessão (formato materializado)
- `.trajectory/export/trace-<trace_id>.json` — payload HTTP que seria enviado ao intake

Markers em `.trajectory/markers.yaml` detectam delegação, lookup de pedido, estoque e política de troca.

## Modo mock vs OpenAI

| Variável | Comportamento |
| --- | --- |
| `USE_MOCK_LLM=auto` (padrão) | Mock se `OPENAI_API_KEY` estiver vazio |
| `USE_MOCK_LLM=true` | Sempre mock |
| `USE_MOCK_LLM=false` | Exige `OPENAI_API_KEY` |

## Variáveis principais

```
DD_LLMOBS_ENABLED=1
DD_LLMOBS_ML_APP=retail-assistant   # igual nos 2 serviços
DD_SERVICE_GATEWAY=retail-gateway
DD_SERVICE_PROCESSOR=retail-processor
TRAJECTORY_EXPORT=true              # false = só JSONL/local
PROCESSOR_URL=http://localhost:8002
```

## Estrutura

```
├── common/                      # LLM, config, ERP mock
│   └── trajectory/              # SDK Trajectory (HTTP LLMObs, sem dd-trace)
├── services/
│   ├── gateway/                 # Agente 1 + API /chat
│   └── processor/               # Agente 2 + API /process
├── .trajectory/markers.yaml     # Markers de comportamento
├── INSTRUMENTATION.md           # Plano de instrumentação
├── scripts/
├── docker-compose.yml
└── docker-compose.prod.yml
```

## Testes

```bash
pip install -r requirements.txt
pytest
```
