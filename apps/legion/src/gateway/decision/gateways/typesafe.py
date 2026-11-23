"""Gateway kind `typesafe`: TypeSafe's Jev API (POST /v1/systemone, bearer key). A cloud call, one call per question."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

from src.gateway.decision.answers import answer_from, mark
from src.gateway.decision.contract import DecisionRequest, GatewayResult, assets_for
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways.base import BaseGateway, upstream_post

NAME = "TypeSafe"
DEFAULT_BAR = 0.9  # Jev reports one confidence and has no thresholds of its own
_QID = "answer"


class TypeSafeGateway(BaseGateway):
    kind = "typesafe"
    images = True
    types = frozenset({"choice", "score", "noul", "box"})

    def _headers(self, with_images: bool) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.entry['api_key']}", "Content-Type": "application/json"}
        if with_images:
            headers["TypeSafe-Danger-Zone-Images"] = "true"  # the API requires it for any request with an image
        return headers

    async def _one(self, request: DecisionRequest, qid: str, spec: dict[str, Any], timeout: float) -> tuple[str, dict[str, Any], int, str]:
        assets = assets_for(request.text, spec, request.assets)
        payload: dict[str, Any] = {"model": self.model, "state": request.text, "questions": {_QID: spec}}
        if assets:
            payload["assets"] = assets
        body = await upstream_post(self._client, self.entry["url"], json=payload, headers=self._headers(bool(assets)),
                                   timeout=timeout, name=NAME)
        try:
            answer = answer_from(spec, body["answers"][_QID])
            usage = body.get("usage") or {}
            tokens = usage.get("input_tokens", 0)
            tokens = tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else 0
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.") from None
        mark(answer, spec, request.min_confidence, DEFAULT_BAR)
        return qid, answer, tokens, str(body.get("model", ""))

    async def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        limit = self.timeout if timeout is None else min(timeout, self.timeout)
        rows = await asyncio.gather(*(self._one(request, qid, spec, limit) for qid, spec in request.questions.items()))
        model = next((m for *_, m in rows if m), self.model)
        return GatewayResult({qid: answer for qid, answer, _, _ in rows}, sum(t for _, _, t, _ in rows), model)

    async def probe(self) -> str:
        parts = urlsplit(self.entry["url"])
        await upstream_post(self._client, f"{parts.scheme}://{parts.netloc}/v1/models", json={},
                            headers=self._headers(False), timeout=10.0, name=NAME, method="GET")
        return "TypeSafe is reachable and accepts the API key."
