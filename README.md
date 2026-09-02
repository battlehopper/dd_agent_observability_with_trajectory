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

## Deploy na AWS EC2

Use `docker-compose.prod.yml`: só o **gateway** fica público na porta **8001**. O processor fala só pela rede Docker. Não há Datadog Agent neste stack — o Trajectory exporta spans direto para o intake HTTP do LLM Observability (saída HTTPS 443).

### 1. Instância e Security Group

| Item | Sugestão |
| --- | --- |
| AMI | Amazon Linux 2023 ou Ubuntu 22.04 |
| Tipo | t3.small ou superior |
| Inbound | SSH (22) do seu IP; TCP **8001** (gateway) |
| Não abrir | Porta **8002** (processor interno) |
| Outbound | HTTPS (443) para Datadog e, se for usar modelo real, OpenAI |

Opcional: Elastic IP para IP fixo.

### 2. Bootstrap na EC2

```bash
ssh -i sua-chave.pem ec2-user@<IP_PUBLICO>   # Ubuntu: ubuntu@<IP>

sudo mkdir -p /opt/llmagent
sudo chown "$USER":"$USER" /opt/llmagent
git clone https://github.com/battlehopper/dd_agent_observability_with_trajectory.git /opt/llmagent
cd /opt/llmagent

# Branch deste PR (enquanto não estiver no main):
# git checkout cursor/retail-trajectory-observability-2ec7

chmod +x scripts/*.sh
./scripts/ec2-setup.sh
# Reconecte o SSH se o script adicionou seu usuário ao grupo docker
```

Equivalente manual:

```bash
sudo ./scripts/ensure-docker.sh
sudo ./scripts/install-compose.sh   # se `docker compose version` falhar
sudo usermod -aG docker "$USER"
```

Erros comuns:

| Sintoma | Correção |
| --- | --- |
| `unknown shorthand flag: 'f' in -f` | Falta Compose v2 → `sudo ./scripts/install-compose.sh` |
| `Cannot connect to the Docker daemon` | `sudo ./scripts/ensure-docker.sh` |
| `No match for argument: docker-compose-plugin` | Amazon Linux 2: use o binário, não o pacote yum |

### 3. Configurar ambiente

```bash
export APP_DIR=/opt/llmagent
cd "$APP_DIR"
ls -la    # deve listar scripts/, services/, docker-compose.prod.yml

cp deploy/.env.ec2.example .env
nano .env   # DD_API_KEY, DD_SITE, DD_ENV=aws-ec2
```

`DD_SITE` tem que ser o do **seu tenant** (ex.: `us5.datadoghq.com`). Site errado → 403 e nenhum trace.

Se `cd /opt/llmagent` falhar, o clone está em outro path:

```bash
find /opt /home -name "docker-compose.prod.yml" 2>/dev/null
```

### 4. Subir (detach)

```bash
cd /opt/llmagent
./scripts/start-prod.sh
```

Equivalente:

```bash
./scripts/compose.sh -f docker-compose.prod.yml up -d --build
./scripts/compose.sh -f docker-compose.prod.yml ps
```

| Comando | Efeito |
| --- | --- |
| `up -d --build` | Sobe em background; pode fechar o SSH |
| `logs --tail=50 gateway` | Últimas linhas e sai |
| `logs -f gateway` | Prende o terminal (só debug) |
| `down` | Para e remove os containers |

### 5. Testar

Na própria EC2 (Amazon Linux, containers já no ar):

```bash
cd /opt/llmagent   # ou o diretório do clone (ex. ~/llmagent)
chmod +x scripts/test-ec2.sh
./scripts/test-ec2.sh
```

Uma mensagem só:

```bash
./scripts/test-ec2.sh "Status do pedido BR-10482 e estoque do SKU-7781"
```

Da sua máquina (substitua `<IP_EC2>`):

```bash
curl -s http://<IP_EC2>:8001/health

curl -s -X POST "http://<IP_EC2>:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Status do pedido BR-10482 e estoque SKU-7781"}'
```

No Datadog, filtre LLM Observability por `ml_app:retail-assistant` e `env:aws-ec2`.

Traces a cada 5 minutos (gateway local):

```bash
git pull
chmod +x scripts/*.sh
./scripts/generate-trace.sh          # um trace agora
./scripts/install-trace-timer.sh     # systemd timer (como root)
# journalctl -u retail-trace-generator.service -n 20
# tail -f /var/log/retail-trace.log
```

### 6. Reinício automático (systemd)

Ajuste `User` e `WorkingDirectory` em `deploy/systemd/retail-multiagent.service` se o path ou o usuário não forem `ec2-user` / `/opt/llmagent` (no Ubuntu o usuário costuma ser `ubuntu`):

```bash
sudo cp deploy/systemd/retail-multiagent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now retail-multiagent
sudo systemctl status retail-multiagent
```

### Boas práticas

- Não commitar `.env`. Em produção real, prefira SSM Parameter Store ou Secrets Manager para `DD_API_KEY`.
- Coloque ALB + HTTPS (ACM) na frente da porta 8001.
- `USE_MOCK_LLM=true` na EC2 evita dependência da OpenAI em demos.

## O que observar no Datadog

| Variável | Onde ver |
| --- | --- |
| `DD_SITE` | Canto inferior esquerdo (ex. US5 → `us5.datadoghq.com`) |
| `DD_LLMOBS_ML_APP` | Nome da app em LLM Observability / Agent Observability |

Se `DD_SITE` estiver errado (ex. `datadoghq.com` numa org US5), o intake retorna API Key invalid (403) e nenhum trace aparece.

**Onde olhar:** LLM Observability / Agent Observability → aplicação `retail-assistant`. Não aparece em APM → Services como um Java/`dd-trace` clássico.

Se o `/chat` funciona na EC2 mas a org continua vazia, rode `./scripts/diagnose-datadog.sh`. A causa mais comum é `DD_API_KEY` vazia **dentro do container** (o `.env` foi preenchido depois do `compose up`, ou o site está errado). Recrie:

```bash
./scripts/compose.sh -f docker-compose.prod.yml up -d --build --force-recreate
curl -s http://127.0.0.1:8001/health
./scripts/test-ec2.sh
```

O `/health` passa a mostrar `api_key_configured`, `dd_site`, `intake_url` e `last_export`.

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
│   ├── ec2-setup.sh
│   ├── ensure-docker.sh
│   ├── install-compose.sh
│   ├── start-prod.sh
│   └── compose.sh
├── docker-compose.yml
└── docker-compose.prod.yml
```

## Testes

```bash
pip install -r requirements.txt
pytest
```
