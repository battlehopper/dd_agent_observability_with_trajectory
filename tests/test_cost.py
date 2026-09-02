from common.cost import token_cost_metrics


def test_token_cost_metrics_are_positive() -> None:
    metrics = token_cost_metrics(1000, 500)
    assert metrics["total_tokens"] == 1500
    assert metrics["input_cost"] == 1000 * 0.15 / 1_000_000
    assert metrics["output_cost"] == 500 * 0.60 / 1_000_000
    assert metrics["total_cost"] == metrics["input_cost"] + metrics["output_cost"]
    assert metrics["estimated_total_cost"] == metrics["total_cost"] * 1_000_000_000
