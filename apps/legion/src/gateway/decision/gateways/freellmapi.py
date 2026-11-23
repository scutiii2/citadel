"""Gateway kind `freellmapi`: FreeLLMAPI's POST /v1/decisions (System One shape, bearer key). One call for all questions.
It routes to a free decision model on its own; set `model` only to pin one (GET /v1/decisions/models lists them)."""
from __future__ import annotations

from typing import Any

from src.gateway.decision.answers import answer_from, default_threshold, mark
from src.gateway.decision.contract import DecisionRequest, GatewayResult
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways.base import BaseGateway, upstream_post

NAME = "FreeLLMAPI"
NOUL_DEFAULT = {"true": "Yes", "false": "No"}


class FreeLLMAPIGateway(BaseGateway):
    kind = "freellmapi"
    types = frozenset({"choice", "score", "noul"})

    def _url(self, path: str) -> str:
        return f"{self.entry['url'].removesuffix('/v1')}/v1{path}"  # the address may or may not end in /v1

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.entry['api_key']}", "Content-Type": "application/json"}

    async def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        limit = self.timeout if timeout is None else min(timeout, self.timeout)
        questions = {qid: ({**spec, "criteria": dict(NOUL_DEFAULT)} if spec["type"] == "noul" and spec.get("criteria") is None else spec)
                     for qid, spec in request.questions.items()}
        payload: dict[str, Any] = {"state": request.text, "questions": questions}
        if self.model:
            payload["model"] = self.model
        body = await upstream_post(self._client, self._url("/decisions"), json=payload, headers=self._headers(),
                                   timeout=limit, name=NAME)
        try:
            answers = {}
            for qid, spec in request.questions.items():
                answer = answer_from(spec, body["answers"][qid])
                mark(answer, spec, request.min_confidence, default_threshold(spec))
                answers[qid] = answer
            tokens = (body.get("usage") or {}).get("input_tokens", 0)
            tokens = tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else 0
            model = body.get("model")
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.") from None
        return GatewayResult(answers, tokens, model if isinstance(model, str) else self.model)

    async def probe(self) -> str:
        await upstream_post(self._client, self._url("/decisions/models"), json={}, headers=self._headers(),
                            timeout=10.0, name=NAME, method="GET")
        return "FreeLLMAPI is reachable and accepts the key."
