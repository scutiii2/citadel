"""Decision gateway `laya`: the shared LayaModel service over HTTP. Legion loads no model.

Which service strategy answers is gateway config (gateways/decision/laya.json `strategy`)."""

from __future__ import annotations

import json
from typing import Any

from src.providers import llm_config
from src.providers.decision import laya_model
from src.providers.decision.contract import DecisionError, DecisionRequest, GatewayResult
from src.providers.decision.laya_model import LayaServiceError

ID = "laya"
WINDOW = 512
MAX_CHARS = 4000
DEFAULT_STRATEGY = "english-then-typed"


class LayaGateway:
    id = ID
    local = True

    def __init__(self, service: Any = None) -> None:
        self._service = service

    def _client(self) -> Any:
        return self._service or laya_model.agent()

    @property
    def strategy(self) -> str:
        """Read from disk on every call, so editing laya.json needs no restart."""
        path = llm_config.GATEWAYS_DIR / "decision" / "laya.json"
        try:
            block = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return DEFAULT_STRATEGY
        except (OSError, ValueError) as error:
            raise DecisionError(f"{path.name} cannot be read as JSON: {error}") from error
        if not isinstance(block, dict):
            raise DecisionError(f"{path.name} must contain a JSON object")
        return str(block.get("strategy") or DEFAULT_STRATEGY)

    def available(self) -> bool:
        return bool(self._client().configured)

    def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        if len(request.text) > MAX_CHARS:
            raise DecisionError(f"Laya takes at most {MAX_CHARS} characters of text")
        strategy = self.strategy
        try:
            body = self._client().ask(strategy, request.text, request.questions, WINDOW,
                                      min_confidence=request.min_confidence, timeout=timeout)
        except LayaServiceError as error:
            raise DecisionError(str(error)) from error
        tokens = sum(call.get("input_tokens") or 0 for call in body.get("calls", []))
        return GatewayResult(body["answers"], tokens, strategy)
