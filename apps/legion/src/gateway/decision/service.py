"""Validates which gateway may answer a request, asks it, and shapes the answer. app.py is only transport glue."""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

import httpx

from src.gateway.decision.answers import compact
from src.gateway.decision.cache import AnswerCache
from src.gateway.decision.contract import DecisionRequest, GatewayResult
from src.gateway.decision.errors import GatewayError
from src.gateway.decision.gateways import BaseGateway, build_gateway
from src.gateway.decision.store import GatewayStore

REACHABLE_SECONDS = 15.0
PROBE_SECONDS = 3.0
TEST_SECONDS = 20.0  # the Test button gives up here; a gateway's own timeout is for questions


class DecisionService:
    def __init__(self, store: GatewayStore, settings: Any, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._store, self._settings, self._transport = store, settings, transport
        self._gateways: dict[str, tuple[dict[str, Any], BaseGateway]] = {}
        self._cache = AnswerCache(lambda: settings.cache_enabled, lambda: settings.cache_seconds, lambda: settings.cache_entries)
        self._inflight = 0
        self._reachable: dict[str, tuple[float, bool]] = {}

    async def _gateway(self, gateway_id: str) -> BaseGateway:
        entry = (await asyncio.to_thread(self._store.all)).get(gateway_id)
        if entry is None:
            self._gateways.pop(gateway_id, None)
            raise GatewayError(422, "unknown_gateway", f"There is no gateway named '{gateway_id}'.")
        cached = self._gateways.get(gateway_id)
        if cached is None or cached[0] != entry:  # rebuilt when the saved entry changed
            self._cache.clear()
            cached = (entry, build_gateway(gateway_id, entry, self._transport))
            self._gateways[gateway_id] = cached
        return cached[1]

    @staticmethod
    def _check(gateway: BaseGateway, request: DecisionRequest) -> None:
        if request.assets and not gateway.images:
            raise GatewayError(422, "images_unsupported", f"The gateway '{gateway.id}' cannot read images.")
        for spec in request.questions.values():
            if spec["type"] not in gateway.types:
                raise GatewayError(422, "type_unsupported", f"The gateway '{gateway.id}' does not answer {spec['type']} questions.")

    def _enter(self) -> None:
        if self._inflight >= self._settings.max_inflight:
            raise GatewayError(429, "busy", "Too many decisions at once.", retry_after=1)
        self._inflight += 1

    def _body(self, gateway: BaseGateway, request: DecisionRequest, result: GatewayResult, streamed: bool) -> dict[str, Any]:
        answers = {}
        for qid, answer in result.answers.items():
            row = {**answer, "answered_by": gateway.id}
            answers[qid] = row if request.trace else compact(row)
        return {"gateway": gateway.id, "model": result.model or gateway.model, "answers": answers,
                "tokens": result.tokens, "streamed": streamed}

    async def decide(self, request: DecisionRequest) -> dict[str, Any]:
        gateway = await self._gateway(request.gateway)
        self._check(gateway, request)
        key = AnswerCache.key(request)
        if (hit := self._cache.get(key)) is not None:
            return hit
        self._enter()
        try:
            result = await gateway.ask(request)
        finally:
            self._inflight -= 1
        body = self._body(gateway, request, result, False)
        self._cache.put(key, body)
        return body

    async def stream(self, request: DecisionRequest) -> AsyncIterator[dict[str, Any]]:
        gateway = await self._gateway(request.gateway)
        self._check(gateway, request)
        key = AnswerCache.key(request)
        hit = self._cache.get(key)
        if hit is None and not gateway.streams:
            hit = await self.decide(request)
        if hit is not None:
            for qid, answer in hit["answers"].items():
                yield {"type": "answer", "id": qid, "answer": answer}
            yield {"type": "done", **hit, "streamed": False}
            return
        self._enter()
        try:
            async for item in gateway.ask_stream(request):
                if item[0] == "answer":
                    _, qid, answer = item
                    row = {**answer, "answered_by": gateway.id}
                    yield {"type": "answer", "id": qid, "answer": row if request.trace else compact(row)}
                else:
                    body = self._body(gateway, request, item[1], True)
                    self._cache.put(key, {**body, "streamed": False})
                    yield {"type": "done", **body}
        finally:
            self._inflight -= 1

    async def _is_reachable(self, gateway: BaseGateway) -> bool:
        seen = self._reachable.get(gateway.id)
        if seen and time.monotonic() - seen[0] < REACHABLE_SECONDS:
            return seen[1]
        try:
            await asyncio.wait_for(gateway.probe(), PROBE_SECONDS)
            ok = True
        except (GatewayError, asyncio.TimeoutError):
            ok = False
        self._reachable[gateway.id] = (time.monotonic(), ok)
        return ok

    async def gateways(self) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(self._store.public)
        built = [await self._gateway(row["id"]) for row in rows]
        reachable = await asyncio.gather(*(self._is_reachable(g) for g in built))
        return [{**row, "streams": g.streams, "images": g.images, "types": sorted(g.types), "reachable": ok}
                for row, g, ok in zip(rows, built, reachable)]

    async def test(self, gateway_id: str) -> str:
        try:
            gateway = await self._gateway(gateway_id)
        except GatewayError:
            raise GatewayError(404, "unknown_gateway", f"There is no gateway named '{gateway_id}'.") from None
        self._reachable.pop(gateway_id, None)
        try:
            return await asyncio.wait_for(gateway.probe(), TEST_SECONDS)
        except asyncio.TimeoutError:
            raise GatewayError(504, "gateway_timeout", f"No answer within {TEST_SECONDS:.0f} seconds. Check the address and that the service is running.") from None
