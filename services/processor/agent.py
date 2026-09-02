"""Agente 2 — especialista retail: consulta ERP mock e responde."""

from __future__ import annotations

from typing import Any

from common.config import Settings
from common.llm import complete_specialist
from common.retail_data import lookup_order, lookup_sku, search_policies
from common.trajectory.tracer import TrajectoryTracer


class SpecialistAgent:
    def __init__(self, settings: Settings, tracer: TrajectoryTracer):
        self.settings = settings
        self.tracer = tracer

    def handle(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        ctx = self.tracer.activate_distributed_headers(headers)
        if ctx is None:
            self.tracer.start_turn()
        user_message = str(payload.get("user_message") or payload.get("summary") or "")
        with self.tracer.span(
            "retail-backoffice-process",
            "workflow",
            semantic_type="turn",
            input_value=user_message,
            extra_tags={
                "trajectory.semantic_name": "retail-backoffice-process",
                "trajectory.subagent_attachment": "launch",
            },
        ) as workflow:
            with self.tracer.span(
                "retail-specialist",
                "agent",
                semantic_type="agent_message",
                input_value=user_message,
            ) as agent:
                context = self._retrieve(payload, user_message)
                result = self._infer(payload, context)
                answer = str(result.get("answer") or "")
                agent.annotate(output_value=answer)
            workflow.annotate(output_value=answer)
        return {
            "answer": answer,
            "session_id": self.tracer.session_id(),
            "context_keys": list(context.keys()),
            "model": result.get("model"),
        }

    def _retrieve(self, payload: dict[str, Any], user_message: str) -> dict[str, Any]:
        with self.tracer.span(
            "retail-knowledge-base",
            "retrieval",
            input_value=user_message,
        ) as retrieval:
            orders = [lookup_order(oid) for oid in payload.get("orders") or []]
            inventory = [lookup_sku(sku) for sku in payload.get("skus") or []]
            policies = search_policies(user_message) if "policy" in (payload.get("intents") or []) else []
            context = {
                "orders": [o for o in orders if o],
                "inventory": [i for i in inventory if i],
                "policies": policies,
            }
            documents: list[dict[str, Any]] = []
            for order in context["orders"]:
                documents.append(
                    {
                        "id": order["order_id"],
                        "name": f"order:{order['order_id']}",
                        "text": str(order),
                        "score": 1.0,
                    }
                )
            for sku in context["inventory"]:
                documents.append(
                    {
                        "id": sku["sku"],
                        "name": f"sku:{sku['sku']}",
                        "text": str(sku),
                        "score": 0.9,
                    }
                )
            for doc in context["policies"]:
                documents.append(
                    {"id": doc["id"], "name": doc["title"], "text": doc["text"], "score": 0.7}
                )
            retrieval.annotate(
                output_documents=documents,
                output_value=f"{len(documents)} documentos ERP",
                metadata={"retriever": "mock-erp"},
            )
            return context

    def _infer(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        with self.tracer.span(
            "specialist-inference",
            "llm",
            extra_tags={"trajectory.llm_call": "true"},
        ) as llm:
            result = complete_specialist(payload, context, self.settings)
            llm.annotate(
                input_messages=[
                    {"role": "system", "content": "retail specialist using ERP context"},
                    {"role": "user", "content": str(payload)},
                ],
                output_messages=[{"role": "assistant", "content": result.get("answer", "")}],
                output_value=result.get("answer"),
                model_name=result.get("model"),
                model_provider=result.get("provider"),
                metrics={
                    "input_tokens": float(result.get("input_tokens") or 0),
                    "output_tokens": float(result.get("output_tokens") or 0),
                    "total_tokens": float(
                        (result.get("input_tokens") or 0) + (result.get("output_tokens") or 0)
                    ),
                },
            )
            return result
