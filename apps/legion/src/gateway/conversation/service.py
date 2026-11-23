"""Validates which gateway may answer a request, asks it, and shapes the reply. app.py is only transport glue."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager, aclosing
from dataclasses import replace
from typing import Any, AsyncIterator

import httpx

from src.gateway.conversation.contract import ChatRequest, ChatResult
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.gateways import BaseGateway, build_gateway
from src.gateway.conversation.store import GatewayStore

REACHABLE_SECONDS = 15.0
PROBE_SECONDS = 3.0
TEST_SECONDS = 20.0  # the Test button gives up here; a gateway's own timeout is for chats
USAGE = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")


class ChatService:
    def __init__(self, store: GatewayStore, settings: Any, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._store, self._settings, self._transport = store, settings, transport
        self._gateways: dict[str, tuple[dict[str, Any], BaseGateway]] = {}
        self._inflight = 0
        self._reachable: dict[str, tuple[float, bool]] = {}
        self._users: dict[BaseGateway, int] = {}
        self._retired: set[BaseGateway] = set()

    async def aclose(self) -> None:
        """Release pools at application shutdown."""
        gateways = {g for _, g in self._gateways.values()} | self._retired
        self._gateways.clear()
        self._retired.clear()
        await asyncio.gather(*(g.aclose() for g in gateways))

    async def _retire(self, gateway: BaseGateway) -> None:
        if self._users.get(gateway, 0):
            self._retired.add(gateway)
        else:
            await gateway.aclose()

    @asynccontextmanager
    async def _lease(self, gateway: BaseGateway):
        """Gateway edits cannot close an active chat or probe."""
        self._users[gateway] = self._users.get(gateway, 0) + 1
        try:
            yield
        finally:
            count = self._users[gateway] - 1
            if count:
                self._users[gateway] = count
            else:
                self._users.pop(gateway, None)
                if gateway in self._retired:
                    self._retired.remove(gateway)
                    await gateway.aclose()

    async def _gateway(self, gateway_id: str) -> BaseGateway:
        entry = (await asyncio.to_thread(self._store.all)).get(gateway_id)
        if entry is None:
            old = self._gateways.pop(gateway_id, None)
            if old:
                await self._retire(old[1])
            raise GatewayError(422, "unknown_gateway", f"There is no gateway named '{gateway_id}'.")
        cached = self._gateways.get(gateway_id)
        if cached is None or cached[0] != entry:  # rebuilt when the saved entry changed
            old = cached
            cached = (entry, build_gateway(gateway_id, entry, self._transport))
            self._gateways[gateway_id] = cached
            self._reachable.pop(gateway_id, None)
            if old:
                await self._retire(old[1])
        return cached[1]

    @classmethod
    def _prepare(cls, gateway: BaseGateway, request: ChatRequest) -> ChatRequest:
        """Apply defaults and ceilings to the effective output limit."""
        if request.tier:  # a tier names the model this gateway saved for it; none saved = the gateway's own model
            request = replace(request, model=(gateway.entry.get("models") or {}).get(request.tier), tier=None)
        cls._check(gateway, request)
        if request.max_tokens is not None:
            return request
        default = gateway.entry.get("default_max_tokens")
        if gateway.provider == "anthropic":
            from src.gateway.conversation.gateways.anthropic import BUDGETS
            default = default or 4096
            if request.reasoning:
                budget = request.reasoning["budget_tokens"] or BUDGETS[request.reasoning["effort"]]
                default = max(default, budget + 1)
        ceiling = gateway.entry.get("max_tokens_limit")
        maximum = min(default, ceiling) if default and ceiling else default or ceiling
        prepared = replace(request, max_tokens=maximum)
        cls._check(gateway, prepared)
        return prepared

    @staticmethod
    def _check(gateway: BaseGateway, request: ChatRequest) -> None:
        for capability in sorted(request.uses):
            if capability == "images" and gateway.forwards_images:
                continue
            if not gateway.can(capability):
                raise GatewayError(422, f"{capability}_unsupported", f"The gateway '{gateway.id}' does not support {capability}.")
        limit = gateway.entry.get("max_tokens_limit")
        if request.max_tokens and limit and request.max_tokens > limit:
            raise GatewayError(422, "max_tokens_too_large", f"The gateway '{gateway.id}' allows at most {limit} max_tokens.")
        gateway.validate(request)

    async def check(self, request: ChatRequest) -> None:
        self._prepare(await self._gateway(request.gateway), request)

    def _enter(self) -> None:
        if self._inflight >= self._settings.max_inflight:
            raise GatewayError(429, "busy", "Too many chats at once.", retry_after=1)
        self._inflight += 1

    @staticmethod
    def _body(gateway: BaseGateway, result: ChatResult, streamed: bool, started: float) -> dict[str, Any]:
        try:
            usage = {k: int(result.usage.get(k) or 0) for k in USAGE}
        except (TypeError, ValueError, OverflowError, AttributeError):
            raise GatewayError(502, "gateway_bad_reply", "The model service sent unusable token counts.", kind="unavailable") from None
        body: dict[str, Any] = {"gateway": gateway.id, "provider": gateway.provider, "model": result.model or gateway.model,
                                "content": result.content}
        if result.reasoning:
            body["reasoning"] = result.reasoning
        if result.reasoning_state:
            body["reasoning_state"] = result.reasoning_state
        body.update(stop_reason=result.stop_reason, usage=usage,
                    duration_ms=round((time.perf_counter() - started) * 1000), streamed=streamed)
        return body

    async def chat(self, request: ChatRequest) -> dict[str, Any]:
        gateway = await self._gateway(request.gateway)
        request = self._prepare(gateway, request)
        self._enter()
        started = time.perf_counter()
        try:
            async with self._lease(gateway):
                result = await gateway.complete(request)
        finally:
            self._inflight -= 1
        return self._body(gateway, result, False, started)

    async def stream(self, request: ChatRequest) -> AsyncIterator[dict[str, Any]]:
        gateway = await self._gateway(request.gateway)
        request = self._prepare(gateway, request)
        self._enter()
        started = time.perf_counter()
        try:
            async with self._lease(gateway):
                async with aclosing(self._stream(gateway, request, started)) as items:
                    async for item in items:
                        yield item
        finally:
            self._inflight -= 1

    async def _stream(self, gateway: BaseGateway, request: ChatRequest, started: float) -> AsyncIterator[dict[str, Any]]:
        if not gateway.can("streams"):  # emulated: the finished answer in the same lines
            result = await gateway.complete(request)
            if result.reasoning:
                yield {"type": "reasoning", "delta": result.reasoning}
            for block in result.content:
                if block["type"] == "text":
                    yield {"type": "text", "delta": block["text"]}
                elif block["type"] == "tool_call":
                    yield {"type": "tool_call", "id": block["id"], "name": block["name"], "arguments_delta": json.dumps(block["arguments"])}
            yield {"type": "done", **self._body(gateway, result, False, started)}
            return
        async with aclosing(gateway.stream(request)) as upstream:
            async for item in upstream:
                if item[0] in ("text", "reasoning"):
                    yield {"type": item[0], "delta": item[1]}
                elif item[0] == "tool_call":
                    yield {"type": "tool_call", "id": item[1], "name": item[2], "arguments_delta": item[3]}
                else:
                    yield {"type": "done", **self._body(gateway, item[1], True, started)}

    async def _is_reachable(self, gateway: BaseGateway) -> bool:
        seen = self._reachable.get(gateway.id)
        if seen and time.monotonic() - seen[0] < REACHABLE_SECONDS:
            return seen[1]
        try:
            async with self._lease(gateway):
                await asyncio.wait_for(gateway.probe(), PROBE_SECONDS)
            ok = True
        except (GatewayError, asyncio.TimeoutError):
            ok = False
        self._reachable[gateway.id] = (time.monotonic(), ok)
        return ok

    async def gateways(self) -> list[dict[str, Any]]:
        rows = await asyncio.to_thread(self._store.public)
        built, current = [], []
        for row in rows:
            try:
                gateway = await self._gateway(row["id"])
            except GatewayError as error:
                if error.code == "unknown_gateway":
                    continue  # deleted after the listing snapshot
                raise
            built.append(gateway)
            current.append(self._store._public(gateway.id, gateway.entry))
        # Only Scuti services are probed on a listing: a probe of a paid provider costs a request.
        # The others show the result of their last Test (nothing until one ran).
        reachable = await asyncio.gather(*(self._is_reachable(g) if g.provider == "scuti" else asyncio.sleep(0, (self._reachable.get(g.id) or (0, None))[1]) for g in built))
        out = []
        for row, g, ok in zip(current, built, reachable):
            item = {**row, **g.capabilities}
            if ok is not None:
                item["reachable"] = ok
            out.append(item)
        return out

    async def models(self, gateway_id: str) -> list[str]:
        try:
            gateway = await self._gateway(gateway_id)
        except GatewayError:
            raise GatewayError(404, "unknown_gateway", f"There is no gateway named '{gateway_id}'.") from None
        async with self._lease(gateway):
            try:
                return await asyncio.wait_for(gateway.models(), TEST_SECONDS)
            except asyncio.TimeoutError:
                raise GatewayError(504, "gateway_timeout", f"No answer within {TEST_SECONDS:.0f} seconds. Check the address and that the service is running.", kind="unavailable") from None

    async def test(self, gateway_id: str) -> str:
        try:
            gateway = await self._gateway(gateway_id)
        except GatewayError:
            raise GatewayError(404, "unknown_gateway", f"There is no gateway named '{gateway_id}'.") from None
        async with self._lease(gateway):
            try:
                message = await asyncio.wait_for(gateway.probe(), TEST_SECONDS)
            except asyncio.TimeoutError:
                self._reachable[gateway_id] = (time.monotonic(), False)
                raise GatewayError(504, "gateway_timeout", f"No answer within {TEST_SECONDS:.0f} seconds. Check the address and that the service is running.", kind="unavailable") from None
            except GatewayError:
                self._reachable[gateway_id] = (time.monotonic(), False)
                raise
        self._reachable[gateway_id] = (time.monotonic(), True)
        return message
