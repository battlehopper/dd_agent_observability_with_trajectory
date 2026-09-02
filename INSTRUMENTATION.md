# Plano de instrumentação — Trajectory no lugar de dd-trace

Este documento descreve **como** o agente retail é observado no Datadog LLM Observability usando o modelo do [Trajectory](https://github.com/datadog-labs/trajectory), sem instalar nem executar `dd-trace` / `ddtrace-run`.

## 1. Por que não dd-trace

O exemplo original (gateway + processor) usa:

```python
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import workflow, agent, task, llm, retrieval

LLMObs.enable(...)
LLMObs.inject_distributed_headers()
LLMObs.activate_distributed_headers(dict(request.headers))
```

Isso acopla APM + LLM Observability no mesmo tracer. O objetivo deste repo é o caminho **Trajectory**:

| Original (dd-trace) | Este repo (Trajectory) |
| --- | --- |
| `ddtrace.llmobs.LLMObs` | `common.trajectory.TrajectoryTracer` |
| Decorators `@workflow` / `@agent` / `@llm` | `with tracer.span(name, kind)` |
| `LLMObs.annotate(...)` | `span.annotate(...)` |
| `LLMObs.inject_distributed_headers()` | `tracer.inject_distributed_headers()` |
| `LLMObs.activate_distributed_headers()` | `tracer.activate_distributed_headers()` |
| Transporte: agent DogStatsD / APM | Transporte: HTTP LLM Observability (o mesmo do Trajectory) |
| Identidade APM `DD_SERVICE` | Tag `service:` + `trajectory.client_source` |

O resultado no produto Datadog continua sendo **Agent / LLM Observability**, não uma UI paralela.

## 2. Transporte e contrato

O Trajectory publica spans no intake:

```
POST https://api.<DD_SITE>/api/intake/llm-obs/v1/trace/spans
Header: DD-API-KEY
```

Payload (`data.type = span`) com `ml_app`, `session_id` e lista de spans. Cada span tem:

- `name`, `span_id`, `trace_id`, `parent_id` (`undefined` na raiz)
- `start_ns`, `duration` (ns)
- `meta.kind` ∈ `workflow | agent | task | tool | retrieval | llm`
- `meta.input` / `meta.output` (`value`, `messages`, `documents`)
- `metrics` (`input_tokens`, `output_tokens`, `total_tokens`, custos)
- `tags` no formato `chave:valor`

IDs: `span_id` 16 hex (64-bit), `trace_id` 32 hex (128-bit), alinhados ao que o intake espera.

Referências:

- [HTTP API — LLM Observability](https://docs.datadoghq.com/llm_observability/instrumentation/api/)
- [LLM-OBS-SPAN-TAGS.md](https://github.com/datadog-labs/trajectory/blob/main/docs/LLM-OBS-SPAN-TAGS.md)
- [SUBAGENT-TRACE-MODEL.md](https://github.com/datadog-labs/trajectory/blob/main/docs/SUBAGENT-TRACE-MODEL.md)

## 3. Mapa de spans do fluxo retail

Uma requisição `POST /chat` gera **um turn** (`trajectory.trace_type:turn`) e **uma sessão** (`trajectory.session_id`).

```
turn root  workflow  retail-customer-chat          service=retail-gateway
 └─ agent            retail-concierge
     ├─ task         enrich-user-intent
     │   └─ llm      concierge-inference           trajectory.llm_call=true
     └─ tool         delegate-to-specialist        subagent_attachment=launch
          └─ workflow retail-backoffice-process    service=retail-processor
               └─ agent retail-specialist          (mesmo trace_id)
                    ├─ retrieval retail-knowledge-base
                    └─ llm       specialist-inference
```

Essa árvore replica a cadeia do README de referência (`workflow → agent → task → retrieval → llm`), com o processor como **subagente síncrono** no sentido Trajectory: o tool `delegate-to-specialist` é o launch; o workflow do processor é filho desse tool via `parent_id` injetado nos headers.

## 4. Tags obrigatórias (contrato Trajectory)

Todo span leva, quando a fonte existe:

| Tag | Origem |
| --- | --- |
| `ml_app` | `DD_LLMOBS_ML_APP` (`retail-assistant`) |
| `service` | `retail-gateway` ou `retail-processor` |
| `trajectory.version` | `TRAJECTORY_VERSION` |
| `host` | hostname |
| `env` | `DD_ENV` |
| `trajectory.client_source` | `retail-multiagent` |
| `trajectory.capture_level` | `full` / `standard` / `minimal` |
| `trajectory.trace_type` | `turn` |
| `trajectory.session_id` | sessão do chat |
| `trajectory.semantic_type` | `turn`, `agent_message`, `task`, `llm`, … |
| `trajectory.llm_call` | `true` só em spans `kind=llm` |
| `gen_ai.request.model` | modelo mock ou OpenAI |

O processor ainda marca `trajectory.subagent_attachment:launch` no workflow remoto, para o filtro de subagentes no LLM Observability.

## 5. Propagação distribuída (substitui headers dd-trace)

O gateway injeta, na chamada HTTP ao processor:

```
x-trajectory-trace-id
x-trajectory-parent-id
x-trajectory-session-id
x-trajectory-ml-app
x-trajectory-span-link
```

O processor **ativa o contexto no início do request**, antes de qualquer span:

```python
tracer.activate_distributed_headers(dict(request.headers))
```

Regras:

1. O `trace_id` e o `session_id` **não são regenerados** no processor.
2. O primeiro span local (`retail-backoffice-process`) usa `parent_id` = span do tool no gateway.
3. O flush HTTP acontece quando o **root local** do serviço termina (não quando o parent remoto termina).
4. Captura local (JSONL) permanece por serviço, com o mesmo `session_id`.

Isso une o fluxo no LLM Observability. Diferente do modelo “links_only” do Trajectory para coding agents (child session como trace separado), aqui o objetivo do demo é **um único trace_id**, como o README original pedia com `llmobs_parent_id`.

## 6. Captura local + export

Dois sinks, independentes:

1. **Local-first** (sempre que `TRAJECTORY_LOCAL_CAPTURE=true`)
   - `.trajectory/sessions/session-<id>.jsonl` — `session_start` e um evento por span
   - `.trajectory/export/trace-<trace_id>.json` — payload idêntico ao POST
2. **Datadog** (`TRAJECTORY_EXPORT=true` e `DD_API_KEY` definido)
   - POST no intake; 202 = aceito
   - sem API key: não falha a request do usuário; só captura local

Não há Agent na porta 8126. Não use `DD_LLMOBS_AGENTLESS_ENABLED` — esse flag é de dd-trace.

## 7. Markers (assinatura Trajectory)

Arquivo `.trajectory/markers.yaml` (schema `version: 2`).

Pontos atuais:

| Marker | Detecta |
| --- | --- |
| `order-lookup` | tool `http_process` + pedido/BR- |
| `inventory-lookup` | tool `http_process` + SKU/estoque |
| `return-policy` | tool `http_process` + troca/devolução |
| `specialist-delegation` | qualquer delegação HTTP |

Os hits entram em `metadata.markers` do workflow do gateway e na resposta de `/chat`. Dá para evoluir para métricas `trajectory.session.*` como o CLI Trajectory faz com `emit: metric`.

## 8. Instrumentação por camada (checklist)

### 8.1 Bootstrap de cada serviço

- [x] Instanciar `TrajectoryTracer(service=...)` no import do FastAPI
- [x] **Não** importar `ddtrace`
- [x] `ml_app` idêntico nos dois processos

### 8.2 Gateway (`services/gateway`)

- [x] `start_turn()` em `/chat` (gera sessão + trace)
- [x] span `workflow` raiz `retail-customer-chat`
- [x] span `agent` `retail-concierge`
- [x] span `task` `enrich-user-intent` + `llm` da inferência
- [x] span `tool` da chamada HTTP, **depois** `inject_distributed_headers()`
- [x] `span.annotate` com input/output e tokens
- [x] avaliar markers no fim do turn

### 8.3 Processor (`services/processor`)

- [x] `activate_distributed_headers` **antes** do primeiro span
- [x] span `workflow` `retail-backoffice-process`
- [x] span `agent` `retail-specialist`
- [x] span `retrieval` com `output.documents` (pedidos, SKUs, políticas)
- [x] span `llm` da resposta

### 8.4 LLM client (`common/llm.py`)

- [x] Mock determinístico (demo sem custo)
- [x] OpenAI opcional
- [x] Devolver `model`, `provider`, `input_tokens`, `output_tokens` para o span `llm`

## 9. O que **não** entra neste plano

- Spans APM HTTP (`fastapi.request`) — sem dd-trace / OpenTelemetry APM. O Service Map clássico **não** aparece. A topologia vive na árvore LLMObs (`service` tag + parent_id).
- Auto-instrumentação OpenAI via `ddtrace`. Chamadas reais precisam do annotate manual (já feito no client).
- Export OTLP GenAI — caminho válido no Datadog, mas fora do contrato Trajectory.
- Coding-agent shims (`trajectory setup` para Claude/Cursor). Este demo é um agente **de aplicação**, não um cliente de IDE.

Se no futuro for preciso correlacionar com APM de verdade, o caminho recomendado é OTLP (`dd-otlp-source=llmobs`) **além** deste export, não voltar a empilhar `ddtrace-run` no mesmo processo sem um desenho explícito de dual-export.

## 10. Validação

1. `pytest` — árvore de spans, headers, markers, `/chat` e2e com mock.
2. `python scripts/demo_client.py` com os dois serviços no ar.
3. Abrir `.trajectory/export/trace-*.json` e conferir `parent_id` do processor = `span_id` do tool.
4. Com `DD_API_KEY` + `DD_SITE` corretos, filtrar LLM Observability por `ml_app:retail-assistant` e `@trajectory.client_source:retail-multiagent`.
5. Confirmar um único `trace_id` cobrindo gateway e processor.

## 11. Ordem de implementação (já aplicada)

1. SDK Trajectory mínimo (`tracer`, `exporter`, `context`, `tags`, `session`, `markers`).
2. Instrumentar processor (retrieval + llm) e validar JSON local.
3. Instrumentar gateway (workflow + agent + task + llm) sem delegação.
4. Ligar headers + tool `delegate-to-specialist`.
5. Markers YAML e testes de contrato.
6. README / compose / demo client.

## 12. Extensões futuras

- Span links explícitos (`meta` / API de links) no modo `links_only`, mantendo traces filhos separados como no Trajectory de coding agents.
- Oversight spans (`trajectory.trace_type:oversight`) para um reviewer de qualidade da resposta.
- Publicar marker metrics (`trajectory.session.specialist_delegations`) via intake de métricas Datadog.
- `TRAJECTORY_CAPTURE_LEVEL=minimal` omitindo prompts/respostas.
