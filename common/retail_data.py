"""Catálogo retail mock (ERP): pedidos, estoque e políticas."""

from __future__ import annotations

from typing import Any

ORDERS: dict[str, dict[str, Any]] = {
    "BR-10482": {
        "order_id": "BR-10482",
        "status": "em_transito",
        "customer": "Ana Costa",
        "items": [{"sku": "SKU-7781", "qty": 1, "name": "Tênis Runner Pro"}],
        "eta": "2026-09-05",
        "carrier": "Loggi",
        "tracking": "LG998221BR",
    },
    "BR-22011": {
        "order_id": "BR-22011",
        "status": "entregue",
        "customer": "Bruno Lima",
        "items": [{"sku": "SKU-3302", "qty": 2, "name": "Camiseta Essential"}],
        "eta": "2026-08-20",
        "carrier": "Correios",
        "tracking": "BR123456789BR",
    },
}

INVENTORY: dict[str, dict[str, Any]] = {
    "SKU-7781": {
        "sku": "SKU-7781",
        "name": "Tênis Runner Pro",
        "on_hand": 14,
        "reserved": 3,
        "warehouse": "CD-SP-01",
        "available": 11,
    },
    "SKU-3302": {
        "sku": "SKU-3302",
        "name": "Camiseta Essential",
        "on_hand": 0,
        "reserved": 0,
        "warehouse": "CD-RJ-02",
        "available": 0,
    },
    "SKU-9010": {
        "sku": "SKU-9010",
        "name": "Jaqueta Windbreak",
        "on_hand": 42,
        "reserved": 2,
        "warehouse": "CD-SP-01",
        "available": 40,
    },
}

POLICIES: list[dict[str, str]] = [
    {
        "id": "return-30d",
        "title": "Troca e devolução",
        "text": "Trocas em até 30 dias com nota fiscal e etiquetas. Itens usados só por defeito de fabricação.",
    },
    {
        "id": "shipping-sla",
        "title": "Prazo de envio",
        "text": "Pedidos confirmados até 15h saem no mesmo dia útil do CD mais próximo.",
    },
    {
        "id": "stock-reserve",
        "title": "Reserva de estoque",
        "text": "Estoque reservado permanece bloqueado por 2 horas após checkout pendente de pagamento.",
    },
]


def lookup_order(order_id: str) -> dict[str, Any] | None:
    return ORDERS.get(order_id.upper())


def lookup_sku(sku: str) -> dict[str, Any] | None:
    return INVENTORY.get(sku.upper())


def search_policies(query: str) -> list[dict[str, str]]:
    q = query.lower()
    hits: list[dict[str, str]] = []
    for doc in POLICIES:
        hay = f"{doc['title']} {doc['text']}".lower()
        if any(token in hay for token in q.split() if len(token) > 3):
            hits.append(doc)
    if not hits and any(k in q for k in ("troca", "devol", "return", "politic", "política")):
        hits = [d for d in POLICIES if d["id"].startswith("return")]
    return hits or POLICIES[:1]
