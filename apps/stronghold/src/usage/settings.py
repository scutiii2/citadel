"""The "usage" and "pricing" blocks of Stronghold's config.

`usage` holds the token limits (0 = unlimited). `pricing` holds model prices per million
tokens; a model without a price has no cost estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UsageSettings:
    six_hour_token_limit: int = 1_000_000
    weekly_token_limit: int = 5_000_000
    # Soft cap on one chat's context, whatever the model allows: at auto_summarize_ratio of it (or of the
    # model's window, if smaller) a chat is summarized before the next question is sent.
    max_context_tokens_per_chat: int = 150_000
    auto_summarize_ratio: float = 0.6

    @classmethod
    def from_config(cls, raw: dict) -> UsageSettings:
        limits = {}
        for name in ("six_hour_token_limit", "weekly_token_limit"):
            value = raw.get(name, getattr(cls, name))
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"usage.{name} must be a whole number, 0 or more (0 = unlimited)")
            limits[name] = value
        context = raw.get("max_context_tokens_per_chat", cls.max_context_tokens_per_chat)
        if isinstance(context, bool) or not isinstance(context, int) or context < 0:
            raise ValueError("usage.max_context_tokens_per_chat must be a whole number, 0 or more")
        ratio = raw.get("auto_summarize_ratio", cls.auto_summarize_ratio)
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 < ratio <= 1:
            raise ValueError("usage.auto_summarize_ratio must be above 0 and at most 1")
        return cls(**limits, max_context_tokens_per_chat=context, auto_summarize_ratio=float(ratio))


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float


@dataclass(frozen=True)
class PricingSettings:
    currency: str = "USD"
    models: dict[str, ModelPrice] = field(default_factory=dict)

    @classmethod
    def from_config(cls, raw: dict) -> PricingSettings:
        currency = raw.get("currency", "USD")
        if currency != "USD":
            raise ValueError("pricing.currency must be USD")
        models = raw.get("models", {})
        if not isinstance(models, dict):
            raise ValueError("pricing.models must be an object")
        prices = {}
        for model, price in models.items():
            if not model.strip():
                raise ValueError(f"pricing.models key must be a non-empty string: {model!r}")
            if not isinstance(price, dict):
                raise ValueError(f"pricing.models.{model} must be an object")
            for side in ("input", "output"):
                value = price.get(side)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"pricing.models.{model}.{side} must be a finite number >= 0")
            prices[model] = ModelPrice(input=float(price["input"]), output=float(price["output"]))
        return cls(currency=currency, models=prices)


class Pricing:
    """Read-time cost estimates; a derived price is never stored."""

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
