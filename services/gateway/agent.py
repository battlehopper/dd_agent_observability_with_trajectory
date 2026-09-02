"""Agente 1 — concierge retail: resume intenção e delega ao especialista."""

from __future__ import annotations

from typing import Any

import httpx

from common.config import Settings
from common.llm import complete_concierge
from common.trajectory.markers import MarkerEngine
from common.trajectory.tracer import TrajectoryTracer


class ConciergeAgent:
    def __init__(self, settings: Settings, tracer: TrajectoryTracer):
        self.settings = settings
        self.tracer = tracer
        self.markers = MarkerEngine.from_path()

    def handle(self, message: str, session_id: str | None = None) -> dict[str, Any]:
        self.tracer.start_turn(session_id)
        tool_events: list[dict[str, Any]] = []
        with self.tracer.span(
            "retail-customer-chat",
            "workflow",
            semantic_type="turn",
            input_value=message,
            extra_tags={"trajectory.semantic_name": "retail-customer-chat"},
        ) as workflow:
            with self.tracer.span(
                "retail-concierge",
                "agent",
                semantic_type="agent_message",
                input_value=message,
            ) as agent:
                intent = self._enrich_intent(message)
                reply: dict[str, Any]
                if intent.get("needs_specialist"):
                    reply = self._delegate(intent, tool_events)
                else:
                    reply = {
                        "answer": intent.get("summary")
                        or "Posso ajudar com pedidos, estoque e políticas de troca.",
                        "source": "concierge",
                    }
                answer = str(reply.get("answer") or "")
                agent.annotate(output_value=answer, metadata={"intents": ",".join(intent.get("intents") or [])})
            hits = self.markers.evaluate(tool_events)
            workflow.annotate(
                output_value=answer,
                metadata={
                    "marker_count": float(len(hits)),
                    "markers": ",".join(h.name for h in hits) if hits else "none",
                },
                tags={"trajectory.marker.hits": str(len(hits))},
            )
        return {
            "answer": answer,
            "session_id": self.tracer.session_id(),
            "intents": intent.get("intents", []),
            "delegated": bool(intent.get("needs_specialist")),
            "markers": [h.name for h in hits],
            "model": intent.get("model"),
        }

    def _enrich_intent(self, message: str) -> dict[str, Any]:
        with self.tracer.span("enrich-user-intent", "task", input_value=message) as task:
            with self.tracer.span(
                "concierge-inference",
                "llm",
                semantic_type="agent_message",
                extra_tags={"trajectory.llm_call": "true"},
            ) as llm:
                result = complete_concierge(message, self.settings)
                llm.annotate(
                    input_messages=[
                        {"role": "system", "content": "retail concierge intent extraction"},
                        {"role": "user", "content": message},
                    ],
                    output_messages=[{"role": "assistant", "content": result.get("summary", "")}],
                    output_value=result.get("summary"),
                    model_name=result.get("model"),
                    model_provider=result.get("provider"),
                    metrics={
                        "input_tokens": float(result.get("input_tokens") or 0),
                        "output_tokens": float(result.get("output_tokens") or 0),
                        "total_tokens": float(
                            (result.get("input_tokens") or 0) + (result.get("output_tokens") or 0)
                        ),
                    },
                    metadata={"temperature": 0.0},
                )
            task.annotate(output_value=result.get("summary"), metadata={"needs_specialist": bool(result.get("needs_specialist"))})
            return result

    def _delegate(self, intent: dict[str, Any], tool_events: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "summary": intent.get("summary"),
            "intents": intent.get("intents"),
            "orders": intent.get("orders"),
            "skus": intent.get("skus"),
            "user_message": intent.get("user_message"),
        }
        with self.tracer.span(
            "delegate-to-specialist",
            "tool",
            input_value=str(payload),
            extra_tags={
                "trajectory.subagent_attachment": "launch",
                "tool": "http_process",
            },
        ) as tool:
            headers = self.tracer.inject_distributed_headers()
            try:
                response = httpx.post(
                    f"{self.settings.processor_url.rstrip('/')}/process",
                    json=payload,
                    headers=headers,
                    timeout=20.0,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                tool.annotate(output_value=str(exc), tags={"error": "true"})
                raise
            answer = str(data.get("answer") or "")
            tool.annotate(
                output_value=answer,
                metadata={
                    "processor_session": str(data.get("session_id") or ""),
                    "subagent": "retail-specialist",
                },
            )
            tool_events.append({"tool": "http_process", "input": payload, "output": answer})
            return data
