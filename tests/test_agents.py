from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from common.config import Settings
from common.trajectory.tracer import TrajectoryTracer
from services.gateway.agent import ConciergeAgent
from services.processor.agent import SpecialistAgent
from services.processor.main import app as processor_app


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.chdir(tmp_path)
    return Settings(
        dd_api_key="",
        dd_llmobs_ml_app="retail-assistant",
        dd_env="test",
        trajectory_export=False,
        trajectory_local_capture=True,
        use_mock_llm="true",
        processor_url="http://processor.test",
    )


def test_specialist_order_and_stock(settings: Settings) -> None:
    tracer = TrajectoryTracer("retail-processor", settings)
    agent = SpecialistAgent(settings, tracer)
    tracer.start_turn("sess-spec")
    result = agent.handle(
        {
            "summary": "pedido e estoque",
            "intents": ["order_status", "inventory"],
            "orders": ["BR-10482"],
            "skus": ["SKU-7781"],
            "user_message": "Status do pedido BR-10482 e estoque do SKU-7781",
        },
        {},
    )
    assert "BR-10482" in result["answer"]
    assert "em_transito" in result["answer"]
    assert "SKU-7781" in result["answer"]
    assert result["context_keys"] == ["orders", "inventory", "policies"]


def test_concierge_delegates_to_processor(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    proc_tracer = TrajectoryTracer("retail-processor", settings)
    specialist = SpecialistAgent(settings, proc_tracer)

    def fake_post(url: str, json=None, headers=None, timeout=None):
        # Reusa o agente de teste (mesmo settings) para manter o tracer isolado.
        payload = json or {}
        result = specialist.handle(payload, headers or {})
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=result, request=request)

    monkeypatch.setattr("services.gateway.agent.httpx.post", fake_post)
    gw = ConciergeAgent(settings, TrajectoryTracer("retail-gateway", settings))
    out = gw.handle("Status do pedido BR-10482 e estoque do SKU-7781")
    assert out["delegated"] is True
    assert "BR-10482" in out["answer"]
    assert "SKU-7781" in out["answer"]
    assert "specialist-delegation" in out["markers"]
    assert "order-lookup" in out["markers"]
    import json

    exports = list(Path(".trajectory/export").glob("trace-*.json"))
    assert exports
    payload = json.loads(exports[0].read_text())
    services = {s["service"] for s in payload["data"]["attributes"]["spans"]}
    kinds = {s["meta"]["kind"] for s in payload["data"]["attributes"]["spans"]}
    assert services == {"retail-gateway", "retail-processor"}
    assert {"workflow", "agent", "task", "llm", "tool", "retrieval"} <= kinds


def test_processor_health() -> None:
    client = TestClient(processor_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instrumentation"] == "trajectory"
    assert body["service"] == "retail-processor"


def test_unknown_order_has_fallback(settings: Settings) -> None:
    tracer = TrajectoryTracer("retail-processor", settings)
    agent = SpecialistAgent(settings, tracer)
    tracer.start_turn("sess-miss")
    result = agent.handle(
        {
            "intents": ["order_status"],
            "orders": ["BR-00000"],
            "skus": [],
            "user_message": "pedido BR-00000",
        },
        {},
    )
    assert "Não encontrei" in result["answer"] or "BR-00000" in result["answer"]
