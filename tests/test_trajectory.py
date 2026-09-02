from __future__ import annotations

from pathlib import Path

import pytest

from common.config import Settings
from common.trajectory.context import TRACE_HEADER, PARENT_HEADER, SESSION_HEADER, extract_context
from common.trajectory.markers import MarkerEngine
from common.trajectory.tracer import ROOT_PARENT_ID, TrajectoryTracer


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.chdir(tmp_path)
    return Settings(
        dd_api_key="",
        dd_llmobs_ml_app="retail-assistant",
        dd_env="test",
        trajectory_export=False,
        trajectory_local_capture=True,
        trajectory_enabled=True,
        use_mock_llm="true",
    )


def test_span_tree_and_payload(settings: Settings) -> None:
    tracer = TrajectoryTracer("retail-gateway", settings)
    tracer.start_turn("sess-test")
    with tracer.span("retail-customer-chat", "workflow") as workflow:
        with tracer.span("retail-concierge", "agent"):
            with tracer.span("concierge-inference", "llm") as llm:
                llm.annotate(
                    input_messages=[{"role": "user", "content": "oi"}],
                    output_messages=[{"role": "assistant", "content": "olá"}],
                    output_value="olá",
                    model_name="mock-retail-concierge",
                    model_provider="mock",
                    metrics={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                )
        workflow.annotate(output_value="olá")

    export_dir = Path(".trajectory/export")
    files = list(export_dir.glob("trace-*.json"))
    assert len(files) == 1
    import json

    payload = json.loads(files[0].read_text())
    spans = payload["data"]["attributes"]["spans"]
    kinds = {s["name"]: s for s in spans}
    assert kinds["retail-customer-chat"]["parent_id"] == ROOT_PARENT_ID
    assert kinds["retail-concierge"]["parent_id"] == kinds["retail-customer-chat"]["span_id"]
    assert kinds["concierge-inference"]["meta"]["kind"] == "llm"
    assert kinds["concierge-inference"]["metrics"]["total_tokens"] == 3.0
    llm_meta = kinds["concierge-inference"]["meta"]
    assert "value" not in llm_meta.get("input", {})
    assert "value" not in llm_meta.get("output", {})
    assert llm_meta["input"]["messages"][0]["content"] == "oi"
    assert kinds["retail-customer-chat"]["span_id"].isdigit()
    assert len(kinds["retail-customer-chat"]["trace_id"]) == 32
    tags = kinds["concierge-inference"]["tags"]
    assert "trajectory.llm_call:true" in tags
    assert "ml_app:retail-assistant" in tags
    assert "trajectory.client_source:retail-multiagent" in tags
    session_file = Path(".trajectory/sessions/session-sess-test.jsonl")
    assert session_file.exists()
    lines = session_file.read_text().strip().splitlines()
    assert any("session_start" in line for line in lines)


def test_distributed_headers_keep_trace(settings: Settings) -> None:
    gw = TrajectoryTracer("retail-gateway", settings)
    proc = TrajectoryTracer("retail-processor", settings)
    gw.start_turn("sess-dist")
    captured: dict[str, str] = {}
    with gw.span("retail-customer-chat", "workflow"):
        with gw.span("delegate-to-specialist", "tool") as tool:
            captured.update(gw.inject_distributed_headers())
            assert captured[TRACE_HEADER] == tool.trace_id
            assert captured[PARENT_HEADER] == tool.span_id
            assert captured[SESSION_HEADER] == "sess-dist"

    ctx = extract_context(captured)
    assert ctx is not None
    proc.activate_distributed_headers(captured)
    with proc.span("retail-backoffice-process", "workflow") as child:
        child.annotate(output_value="ok")
        assert child.trace_id == captured[TRACE_HEADER]
        assert child.parent_id == captured[PARENT_HEADER]

    import json

    proc_payloads = []
    for path in Path(".trajectory/export").glob("trace-*.json"):
        data = json.loads(path.read_text())
        for span in data["data"]["attributes"]["spans"]:
            if span["service"] == "retail-processor":
                proc_payloads.append(span)
    assert proc_payloads
    assert proc_payloads[0]["parent_id"] != ROOT_PARENT_ID
    assert proc_payloads[0]["parent_id"] == captured[PARENT_HEADER]


def test_markers_detect_delegation() -> None:
    engine = MarkerEngine.from_path(Path("/workspace/.trajectory/markers.yaml"))
    hits = engine.evaluate(
        [
            {
                "tool": "http_process",
                "input": {"user_message": "Status do pedido BR-10482 e estoque SKU-7781"},
                "output": "ok",
            }
        ]
    )
    names = {h.name for h in hits}
    assert "specialist-delegation" in names
    assert "order-lookup" in names
    assert "inventory-lookup" in names
