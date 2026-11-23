"""Gateway kind `ollama`: a decision model (d3) served by Ollama through /v1/systemone. d3 refuses /api/generate; it
needs criteria on every noul question; Ollama loads the model on the first call."""
from __future__ import annotations

from typing import Any

from src.gateway.decision.answers import answer_from, default_threshold, mark
from src.gateway.decision.contract import DecisionRequest, GatewayResult
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways.base import BaseGateway, upstream_post

NAME = "Ollama"
NOUL_DEFAULT = {"true": "Yes", "false": "No"}


def _not_ready() -> GatewayError:
    return GatewayError(503, "gateway_not_ready", "The model is unavailable: start Ollama and pull the model.")


class OllamaGateway(BaseGateway):
    kind = "ollama"
    types = frozenset({"choice", "score", "noul"})

    async def _call(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        try:
            body = await upstream_post(self._client, f"{self.entry['url']}{path}", json=payload,
                                       headers={"Content-Type": "application/json"}, timeout=timeout, name=NAME)
        except GatewayError as error:
            if error.code in ("gateway_unreachable", "gateway_error"):
                raise _not_ready() from None
            raise
        if body.get("error"):
            raise _not_ready()
        return body

    async def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        limit = self.timeout if timeout is None else min(timeout, self.timeout)
        questions = {qid: ({**spec, "criteria": dict(NOUL_DEFAULT)} if spec["type"] == "noul" and spec.get("criteria") is None else spec)
                     for qid, spec in request.questions.items()}
        body = await self._call("/v1/systemone", {"model": self.model, "state": request.text, "questions": questions}, limit)
        try:
            answers = {}
            for qid, spec in request.questions.items():
                answer = answer_from(spec, body["answers"][qid])
                mark(answer, spec, request.min_confidence, default_threshold(spec))
                answers[qid] = answer
            tokens = (body.get("usage") or {}).get("input_tokens", 0)
            tokens = tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else 0
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.") from None
        return GatewayResult(answers, tokens, self.model)

    async def probe(self) -> str:
        await self._call("/api/show", {"model": self.model}, 10.0)
        return "Ollama is reachable and the model is installed."
