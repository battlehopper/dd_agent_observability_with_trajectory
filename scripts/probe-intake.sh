#!/usr/bin/env bash
# Envia um span mínimo ao intake LLM Observability (US5 ou DD_SITE do .env).
# Rode na EC2, no diretório do projeto. Não imprime a API key.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY'
import json, os, time, secrets
from pathlib import Path

def load_env(path: Path) -> dict[str, str]:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

env = {**load_env(Path(".env")), **os.environ}
api_key = env.get("DD_API_KEY", "")
site = env.get("DD_SITE", "us5.datadoghq.com").replace("https://", "").replace("http://", "").removeprefix("app.").removeprefix("api.")
ml_app = env.get("DD_LLMOBS_ML_APP", "retail-assistant")
dd_env = env.get("DD_ENV", "aws-ec2")
url = f"https://api.{site}/api/intake/llm-obs/v1/trace/spans"

if not api_key:
    raise SystemExit("DD_API_KEY vazia no .env")

span_id = str(secrets.randbits(64))
trace_id = f"{secrets.randbits(128):032x}"
now = time.time_ns()
payload = {
    "data": {
        "type": "span",
        "attributes": {
            "ml_app": ml_app,
            "session_id": "probe-ec2",
            "tags": [f"service:retail-gateway", f"env:{dd_env}", "source:probe"],
            "spans": [
                {
                    "name": "retail-customer-chat",
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "parent_id": "undefined",
                    "start_ns": now,
                    "duration": 5_000_000.0,
                    "status": "ok",
                    "service": "retail-gateway",
                    "ml_app": ml_app,
                    "session_id": "probe-ec2",
                    "meta": {
                        "kind": "workflow",
                        "input": {"value": "probe from EC2"},
                        "output": {"value": "probe ok"},
                    },
                }
            ],
        },
    }
}

try:
    import httpx
    resp = httpx.post(url, headers={"DD-API-KEY": api_key, "Content-Type": "application/json"}, json=payload, timeout=15.0)
    status, body = resp.status_code, resp.text[:400]
except Exception as exc:
    status, body = "ERR", str(exc)

print(f"intake: {url}")
print(f"ml_app: {ml_app}  env: {dd_env}  key_len: {len(api_key)}")
print(f"http: {status}")
print(f"body: {body!r}")
if status in (200, 202):
    print("Intake ACEITOU o span. Abra no Datadog US5:")
    print(f"  https://app.{site}/llm/traces")
    print("  LLM Observability → Traces → ml_app:" + ml_app + "  env:" + dd_env)
else:
    print("Intake REJEITOU. 403 = site/chave errados. 400 = payload. timeout = egress 443.")
PY
