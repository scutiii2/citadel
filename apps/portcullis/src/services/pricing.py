"""Read-time cost estimates; never write derived prices into chat history.

Stronghold owns the price table (its `pricing` setting). Portcullis asks for it, keeps the
last answer for a minute and prices chat messages it reads from its own database with it.
"""

import logging
import math
import time
from typing import Any

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 60.0


class Pricing:
    def __init__(self, document: dict[str, Any] | None = None) -> None:
        self.currency = "USD"
        self._models: dict[str, tuple[float, float]] = {}
        self._folded: dict[str, tuple[float, float]] = {}
        self._asked_at: float | None = None
        self.update(document or {})

    def update(self, document: dict[str, Any]) -> None:
        """Replace the table with Stronghold's `{"currency", "models": {name: {"input", "output"}}}`."""
        models: dict[str, tuple[float, float]] = {}
        for model, price in (document.get("models") or {}).items():
            try:
                pair = (float(price["input"]), float(price["output"]))
            except (KeyError, TypeError, ValueError):
                continue
            if all(math.isfinite(value) and value >= 0 for value in pair):
                models[str(model)] = pair
        self.currency = str(document.get("currency") or "USD")
        self._models = models
        self._folded = {model.casefold(): price for model, price in models.items()}

    async def refresh(self, stronghold: Any) -> None:
        """Ask Stronghold for the table when the last answer is older than a minute.
        A failure keeps the last table, so chat reads never fail on pricing."""
        now = time.monotonic()
        if self._asked_at is not None and now - self._asked_at < REFRESH_SECONDS:
            return
        self._asked_at = now
        try:
            answer = await stronghold.forward("GET", "/usage/pricing", None)
            if answer.status == 200:
                import json

                self.update(json.loads(answer.body))
        except Exception as error:  # noqa: BLE001 - pricing must never break a chat read
            logger.warning("could not read prices from stronghold: %s", type(error).__name__)

    def cost(self, model: str | None, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if not model or (input_tokens is None and output_tokens is None):
            return None
        price = self._models.get(model) or self._folded.get(model.casefold())
        if price is None:
            return None
        return ((input_tokens or 0) * price[0] + (output_tokens or 0) * price[1]) / 1_000_000


def with_cost(message: dict[str, Any], pricing: Pricing) -> dict[str, Any]:
    """Copy a message and its agent rows, repricing any stale derived values."""
    result = {key: value for key, value in message.items() if key != "cost"}
    cost = pricing.cost(message.get("model"), message.get("input_tokens"), message.get("output_tokens"))
    if cost is not None:
        result["cost"] = cost
    if isinstance(message.get("agent_usage"), list):
        result["agent_usage"] = [with_cost(row, pricing) for row in message["agent_usage"]]
    return result
