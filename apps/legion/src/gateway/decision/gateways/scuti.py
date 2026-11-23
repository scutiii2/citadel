"""Gateway kind `scuti`: a DSC_* model service (DSC_Laya_Model, DSC_D3_Model). Both answer the Laya-shaped POST /v1/ask."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from src.gateway.decision.contract import DecisionRequest, GatewayResult
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways.base import BaseGateway, raise_for_status, upstream_post

NAME = "The model service"
BUSY_RETRIES = 2
MAX_WAIT = 10.0


def _body(entry: dict[str, Any], request: DecisionRequest, stream: bool) -> dict[str, Any]:
    body: dict[str, Any] = {"text": request.text, "questions": request.questions, "trace": request.trace}
    if entry.get("strategy"):
        body["strategy"] = entry["strategy"]
    if entry.get("window"):
        body["max_len"] = entry["window"]
    if request.min_confidence is not None:
        body["min_confidence"] = request.min_confidence
    if stream:
        body["stream"] = True
    return body


def _result(entry: dict[str, Any], body: dict[str, Any]) -> GatewayResult:
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.")
    tokens = sum(c.get("input_tokens") or 0 for c in body.get("calls", []) if isinstance(c, dict))
    return GatewayResult(answers, tokens, str(body.get("model") or body.get("strategy") or entry.get("model", "")))


class ScutiGateway(BaseGateway):
    kind = "scuti"
    streams = True

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self.entry["token"]} if self.entry.get("token") else {}

    @staticmethod
    def _wait(reply_headers: httpx.Headers) -> float:
        try:
            wait = float(reply_headers.get("retry-after", ""))
        except ValueError:
            wait = 1.0
        return min(max(wait, 0.0), MAX_WAIT)

    async def ask(self, request: DecisionRequest, timeout: float | None = None) -> GatewayResult:
        limit = self.timeout if timeout is None else min(timeout, self.timeout)
        url, payload = f"{self.entry['url']}/v1/ask", _body(self.entry, request, False)
        for attempt in range(BUSY_RETRIES + 1):
            try:
                reply = await self._client.post(url, json=payload, headers=self._headers(), timeout=limit)
            except httpx.HTTPError:
                raise GatewayError(502, "gateway_unreachable", f"{NAME} could not be reached.") from None
            if reply.status_code != 429 or attempt == BUSY_RETRIES:
                break
            await asyncio.sleep(self._wait(reply.headers))
        raise_for_status(reply.status_code, NAME)
        try:
            body = reply.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.")
        return _result(self.entry, body)

    async def ask_stream(self, request: DecisionRequest, timeout: float | None = None) -> AsyncIterator[tuple]:
        limit = self.timeout if timeout is None else min(timeout, self.timeout)
        try:
            async with self._client.stream("POST", f"{self.entry['url']}/v1/ask", json=_body(self.entry, request, True),
                                           headers=self._headers(), timeout=limit) as reply:
                if reply.status_code >= 400:
                    await reply.aread()
                    raise_for_status(reply.status_code, NAME)
                async for line in reply.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.") from None
                    kind = item.get("type") if isinstance(item, dict) else None
                    if kind == "answer" and isinstance(item.get("answer"), dict):
                        yield "answer", str(item.get("id")), item["answer"]
                    elif kind == "done":
                        yield "done", _result(self.entry, item)
                        return
                    elif kind == "error":
                        raise GatewayError(502, "gateway_error", f"{NAME} stopped answering.")
                raise GatewayError(502, "gateway_bad_reply", f"{NAME} ended its reply before completion.")
        except httpx.HTTPError:
            raise GatewayError(502, "gateway_unreachable", f"{NAME} could not be reached.") from None

    async def probe(self) -> str:
        body = await upstream_post(self._client, f"{self.entry['url']}/health", json={}, headers={}, timeout=10.0, name=NAME, method="GET")
        if body.get("ready") is False:
            raise GatewayError(503, "gateway_not_ready", f"{NAME} is running but not ready (its model is not loaded).")
        return "The model service is reachable and ready."
