"""API do processor (porta 8002)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel

from common.config import get_settings
from common.trajectory.tracer import TrajectoryTracer
from services.processor.agent import SpecialistAgent

settings = get_settings()
tracer = TrajectoryTracer(service=settings.dd_service_processor, settings=settings)
agent = SpecialistAgent(settings, tracer)

app = FastAPI(title="retail-processor", version="0.1.0")


class ProcessRequest(BaseModel):
    summary: str | None = None
    intents: list[str] = []
    orders: list[str] = []
    skus: list[str] = []
    user_message: str | None = None


class ProcessResponse(BaseModel):
    answer: str
    session_id: str
    context_keys: list[str]
    model: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.dd_service_processor,
        "ml_app": settings.dd_llmobs_ml_app,
        "instrumentation": "trajectory",
    }


@app.post("/process", response_model=ProcessResponse)
async def process(req: ProcessRequest, request: Request) -> ProcessResponse:
    payload: dict[str, Any] = req.model_dump()
    result = agent.handle(payload, dict(request.headers))
    return ProcessResponse(**result)
