"""A decision gateway saved in DecisionGateway, asked by its id.

Its address, key, model, strategy, window and timeout are saved there. Legion asks `laya` (the local model service)
only about text it can read."""

from __future__ import annotations

from src.providers.decision import gateway_client
from src.providers.decision.contract import DecisionError, DecisionRequest, GatewayResult

# The Laya checkpoints read a 4096-token window; longer text is refused before any call.
LAYA_MAX_CHARS = 4000


class SavedGateway:
    def __init__(self, id: str) -> None:
        self.id = id

    @property
    def local(self) -> bool:
        return gateway_client.is_local(self.id)

    def available(self) -> bool:
        return gateway_client.is_usable(self.id)

    def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        if self.id == "laya" and len(request.text) > LAYA_MAX_CHARS:
            raise DecisionError(f"{self.id} takes at most {LAYA_MAX_CHARS} characters of text")
        own = gateway_client.timeout_of(self.id)
        reply = gateway_client.decide(self.id, request.text, request.questions,
                                      min_confidence=request.min_confidence, timeout=min(timeout or own, own))
        tokens = reply.get("tokens")
        return GatewayResult(reply["answers"], tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else 0,
                             str(reply.get("model") or self.id))
