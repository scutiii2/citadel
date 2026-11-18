"""A decision gateway saved in DecisionGateway, asked by its id.

`laya` is the local model service (text stays on this machine's network) and
`jev` is TypeSafe's cloud API. Their addresses, keys, model, strategy and
window are saved in DecisionGateway; Legion only knows the two ids, which one
is local, and how long to wait for each."""

from __future__ import annotations

from src.providers.decision import gateway_client
from src.providers.decision.contract import DecisionError, DecisionRequest, GatewayResult

# The Laya checkpoints read a 4096-token window; longer text is refused before any call.
LAYA_MAX_CHARS = 4000


class SavedGateway:
    def __init__(self, id: str, *, local: bool, default_timeout: float, max_chars: int | None = None) -> None:
        self.id = id
        self.local = local
        self._default_timeout = default_timeout
        self._max_chars = max_chars

    def available(self) -> bool:
        return gateway_client.is_usable(self.id)

    def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        if self._max_chars is not None and len(request.text) > self._max_chars:
            raise DecisionError(f"{self.id} takes at most {self._max_chars} characters of text")
        reply = gateway_client.decide(self.id, request.text, request.questions,
                                      min_confidence=request.min_confidence,
                                      timeout=min(timeout or self._default_timeout, self._default_timeout))
        tokens = reply.get("tokens")
        return GatewayResult(reply["answers"], tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else 0,
                             str(reply.get("model") or self.id))


def laya() -> SavedGateway:
    return SavedGateway("laya", local=True, default_timeout=60.0, max_chars=LAYA_MAX_CHARS)


def jev() -> SavedGateway:
    return SavedGateway("jev", local=False, default_timeout=3.0)
