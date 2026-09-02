"""Custo estimado de tokens para LLM Observability (USD).

O Datadog só deriva custo sozinho quando o model_name está na tabela de preços
(gpt-4o, claude, …). O mock usa nomes locais, então o custo precisa ir no span
como input_cost / output_cost / total_cost.
"""

from __future__ import annotations

from typing import Any

# Referência pública gpt-4o-mini (USD / 1M tokens). É estimativa, não fatura.
INPUT_USD_PER_MILLION = 0.15
OUTPUT_USD_PER_MILLION = 0.60
RATE_CARD = "gpt-4o-mini-public"


def token_cost_metrics(input_tokens: float, output_tokens: float) -> dict[str, float]:
    inp = float(input_tokens or 0)
    out = float(output_tokens or 0)
    input_cost = inp * INPUT_USD_PER_MILLION / 1_000_000
    output_cost = out * OUTPUT_USD_PER_MILLION / 1_000_000
    total_cost = input_cost + output_cost
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "estimated_total_cost": total_cost * 1_000_000_000,  # nanodólares (contrato Trajectory)
    }


def llm_cost_tags() -> dict[str, str]:
    return {
        "trajectory.cost_status": "priced",
        "trajectory.cost_source": "token_derived",
        "trajectory.pricing_source": RATE_CARD,
        "trajectory.cost_method": "token_rate_card",
    }


def llm_cost_metadata(metrics: dict[str, float]) -> dict[str, Any]:
    return {
        "estimated_total_cost_usd": f"{metrics['total_cost']:.10f}",
        "pricing_source": RATE_CARD,
    }
