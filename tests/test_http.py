from __future__ import annotations

import importlib
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from common.config import get_settings


def test_gateway_health_and_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TRAJECTORY_EXPORT", "false")
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("DD_API_KEY", "")
    get_settings.cache_clear()

    import services.gateway.main as gw_main
    import services.processor.agent as proc_agent_mod
    from common.trajectory.tracer import TrajectoryTracer

    importlib.reload(gw_main)

    settings = get_settings()
    specialist = proc_agent_mod.SpecialistAgent(
        settings, TrajectoryTracer(settings.dd_service_processor, settings)
    )

    def fake_post(url: str, json=None, headers=None, timeout=None):
        result = specialist.handle(json or {}, headers or {})
        request = httpx.Request("POST", url)
        return httpx.Response(200, json=result, request=request)

    monkeypatch.setattr("services.gateway.agent.httpx.post", fake_post)
    client = TestClient(gw_main.app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["instrumentation"] == "trajectory"
    assert health.json()["api_key_configured"] is False

    chat = client.post(
        "/chat",
        json={"message": "Status do pedido BR-10482 e estoque do SKU-7781"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["delegated"] is True
    assert "BR-10482" in body["answer"]
    assert body["session_id"]
