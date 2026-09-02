"""API do gateway (porta 8001)."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from common.config import get_settings
from common.trajectory.tracer import TrajectoryTracer
from services.gateway.agent import ConciergeAgent

settings = get_settings()
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


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.dd_service_gateway,
        "ml_app": settings.dd_llmobs_ml_app,
        "instrumentation": "trajectory",
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    result = agent.handle(req.message, session_id=req.session_id)
    return ChatResponse(**result)
