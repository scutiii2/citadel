"""Read-time cost estimates; never write derived prices into chat history."""

from typing import Any

from src.config import PricingSettings


class Pricing:
    def __init__(self, settings: PricingSettings) -> None:
        self.currency = settings.currency
        self._models = dict(settings.models)
        self._folded = {model.casefold(): price for model, price in self._models.items()}

    def cost(self, model: str | None, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if not model or (input_tokens is None and output_tokens is None):
            return None
        price = self._models.get(model) or self._folded.get(model.casefold())
        if price is None:
            return None
        return ((input_tokens or 0) * price.input + (output_tokens or 0) * price.output) / 1_000_000


def with_cost(message: dict[str, Any], pricing: Pricing) -> dict[str, Any]:
    """Copy a message and its agent rows, repricing any stale derived values."""
    result = {key: value for key, value in message.items() if key != "cost"}
    cost = pricing.cost(message.get("model"), message.get("input_tokens"), message.get("output_tokens"))
    if cost is not None:
        result["cost"] = cost
    if isinstance(message.get("agent_usage"), list):
        result["agent_usage"] = [with_cost(row, pricing) for row in message["agent_usage"]]
    return result
