"""Propagação distribuída de contexto Trajectory (substitui LLMObs.inject/activate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

TRACE_HEADER = "x-trajectory-trace-id"
PARENT_HEADER = "x-trajectory-parent-id"
SESSION_HEADER = "x-trajectory-session-id"
ML_APP_HEADER = "x-trajectory-ml-app"
SPAN_LINK_HEADER = "x-trajectory-span-link"


@dataclass(frozen=True)
class DistributedContext:
    trace_id: str
    parent_id: str
    session_id: str
    ml_app: str = ""
    span_link: str = ""

    def as_headers(self) -> dict[str, str]:
        headers = {
            TRACE_HEADER: self.trace_id,
            PARENT_HEADER: self.parent_id,
            SESSION_HEADER: self.session_id,
        }
        if self.ml_app:
            headers[ML_APP_HEADER] = self.ml_app
        if self.span_link:
            headers[SPAN_LINK_HEADER] = self.span_link
        return headers


def extract_context(headers: Mapping[str, str]) -> DistributedContext | None:
    normalized = {k.lower(): v for k, v in headers.items()}
    trace_id = normalized.get(TRACE_HEADER)
    parent_id = normalized.get(PARENT_HEADER)
    session_id = normalized.get(SESSION_HEADER)
    if not (trace_id and parent_id and session_id):
        return None
    return DistributedContext(
        trace_id=trace_id,
        parent_id=parent_id,
        session_id=session_id,
        ml_app=normalized.get(ML_APP_HEADER, ""),
        span_link=normalized.get(SPAN_LINK_HEADER, ""),
    )
