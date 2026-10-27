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
# Token window both Laya checkpoints read; the service answers 413 for text that does not fit it (it accepts 16-8192).
DEFAULT_WINDOW = 4096
MIN_WINDOW, MAX_WINDOW = 16, 8192
MAX_CHARS = 4000
DEFAULT_STRATEGY = "english-then-typed"


class LayaGateway:
    id = ID
    local = True

    def __init__(self, service: Any = None) -> None:
        self._service = service

    def _client(self) -> Any:
        return self._service or laya_model.agent()

    @staticmethod
    def _settings() -> dict[str, Any]:
        """laya.json, read from disk on every call so editing it needs no restart."""
        path = llm_config.GATEWAYS_DIR / "decision" / "laya.json"
        try:
            block = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            raise DecisionError(f"{path.name} cannot be read as JSON: {error}") from error
        if not isinstance(block, dict):
            raise DecisionError(f"{path.name} must contain a JSON object")
        return block

    @property
    def strategy(self) -> str:
        return str(self._settings().get("strategy") or DEFAULT_STRATEGY)

    @property
    def window(self) -> int:
        value = self._settings().get("window", DEFAULT_WINDOW)
        if isinstance(value, bool) or not isinstance(value, int) or not MIN_WINDOW <= value <= MAX_WINDOW:
            raise DecisionError(f"laya.json window must be a whole number from {MIN_WINDOW} to {MAX_WINDOW}")
        return value

    def available(self) -> bool:
        return bool(self._client().configured)

    def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        if len(request.text) > MAX_CHARS:
            raise DecisionError(f"Laya takes at most {MAX_CHARS} characters of text")
        strategy, window = self.strategy, self.window
        try:
            body = self._client().ask(strategy, request.text, request.questions, window,
                                      min_confidence=request.min_confidence, timeout=timeout)
        except LayaServiceError as error:
            raise DecisionError(str(error)) from error
        tokens = sum(call.get("input_tokens") or 0 for call in body.get("calls", []))
        return GatewayResult(body["answers"], tokens, strategy)
