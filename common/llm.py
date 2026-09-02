"""Cliente LLM: mock determinístico ou OpenAI, conforme configuração."""

from __future__ import annotations

import json
import re
from typing import Any

from common.config import Settings, get_settings

ORDER_RE = re.compile(r"\b(BR-\d{4,})\b", re.IGNORECASE)
SKU_RE = re.compile(r"\b(SKU-[\w-]+)\b", re.IGNORECASE)


def _extract_ids(text: str) -> dict[str, list[str]]:
    return {
        "orders": [m.group(1).upper() for m in ORDER_RE.finditer(text)],
        "skus": [m.group(1).upper() for m in SKU_RE.finditer(text)],
    }


def _mock_concierge(user_message: str) -> dict[str, Any]:
    ids = _extract_ids(user_message)
    lower = user_message.lower()
    intents: list[str] = []
    if ids["orders"] or "pedido" in lower or "order" in lower:
        intents.append("order_status")
    if ids["skus"] or "estoque" in lower or "sku" in lower:
        intents.append("inventory")
    if any(k in lower for k in ("troca", "devol", "política", "politica", "return")):
        intents.append("policy")
    if not intents:
        intents = ["general"]
    summary = (
        f"Intenção(ões): {', '.join(intents)}. "
        f"Pedidos={ids['orders'] or '-'} SKUs={ids['skus'] or '-'}"
    )
    return {
        "role": "concierge",
        "summary": summary,
        "intents": intents,
        "orders": ids["orders"],
        "skus": ids["skus"],
        "needs_specialist": intents != ["general"],
        "user_message": user_message,
        "model": "mock-retail-concierge",
        "provider": "mock",
        "input_tokens": max(8, len(user_message.split())),
        "output_tokens": max(12, len(summary.split())),
    }


def _mock_specialist(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    parts: list[str] = []
    for order in context.get("orders", []):
        parts.append(
            f"Pedido {order['order_id']}: status={order['status']}, "
            f"ETA={order.get('eta')}, tracking={order.get('tracking')}."
        )
    for sku in context.get("inventory", []):
        parts.append(
            f"SKU {sku['sku']} ({sku['name']}): disponível={sku['available']} "
            f"em {sku['warehouse']}."
        )
    for doc in context.get("policies", []):
        parts.append(f"Política '{doc['title']}': {doc['text']}")
    if not parts:
        parts.append("Não encontrei o pedido/SKU no ERP mock. Peça um ID válido (ex.: BR-10482, SKU-7781).")
    answer = " ".join(parts)
    return {
        "role": "specialist",
        "answer": answer,
        "model": "mock-retail-specialist",
        "provider": "mock",
        "input_tokens": 48,
        "output_tokens": max(16, len(answer.split())),
    }


def complete_concierge(user_message: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    if settings.mock_llm:
        return _mock_concierge(user_message)
    return _openai_concierge(user_message, settings)


def complete_specialist(
    payload: dict[str, Any],
    context: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if settings.mock_llm:
        return _mock_specialist(payload, context)
    return _openai_specialist(payload, context, settings)


def _openai_concierge(user_message: str, settings: Settings) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "Você é o concierge de um varejo. Extraia intenções (order_status, inventory, policy, general), "
        "IDs de pedido (BR-xxxx) e SKUs. Responda APENAS JSON com chaves: "
        "summary, intents, orders, skus, needs_specialist (bool)."
    )
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        temperature=0,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = _mock_concierge(user_message)
    usage = resp.usage
    data.update(
        {
            "role": "concierge",
            "user_message": user_message,
            "model": settings.openai_model,
            "provider": "openai",
            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        }
    )
    data.setdefault("needs_specialist", True)
    data.setdefault("intents", ["general"])
    data.setdefault("orders", [])
    data.setdefault("skus", [])
    data.setdefault("summary", content)
    return data


def _openai_specialist(
    payload: dict[str, Any], context: dict[str, Any], settings: Settings
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "Você é o especialista de backoffice retail. Use o contexto ERP JSON para responder "
        "em português, de forma objetiva, ao pedido do concierge."
    )
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps({"request": payload, "erp": context}, ensure_ascii=False),
            },
        ],
        temperature=0,
    )
    answer = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "role": "specialist",
        "answer": answer,
        "model": settings.openai_model,
        "provider": "openai",
        "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
    }
