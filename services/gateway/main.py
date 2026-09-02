"""API do gateway (porta 8001)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from common.config import get_settings
from common.logging_setup import configure_logging
from common.trajectory.tracer import TrajectoryTracer
from services.gateway.agent import ConciergeAgent

settings = get_settings()
configure_logging(settings, settings.dd_service_gateway)
tracer = TrajectoryTracer(service=settings.dd_service_gateway, settings=settings)
agent = ConciergeAgent(settings, tracer)

app = FastAPI(title="retail-gateway", version="0.1.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    intents: list[str]
    delegated: bool
    markers: list[str]
    model: str | None = None
    observability: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.dd_service_gateway,
        "ml_app": settings.dd_llmobs_ml_app,
        "instrumentation": "trajectory",
        **tracer.exporter.status(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    result = agent.handle(req.message, session_id=req.session_id)
    result["observability"] = tracer.exporter.status()
    return ChatResponse(**result)
