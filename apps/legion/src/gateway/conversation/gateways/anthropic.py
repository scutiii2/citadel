"""Provider `anthropic`: the Messages API through the official SDK. Auth variants: key (also gateways such as
OpenRouter, LiteLLM, Helicone, Portkey, OmniRoute through base_url), bedrock and vertex."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock, AsyncAnthropicVertex

from src.gateway.conversation.contract import ChatRequest, ChatResult
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.gateways.base import BaseGateway, truncated
from src.gateway.conversation.gateways.sdk_http import sdk_client

BUDGETS = {"low": 1024, "medium": 4096, "high": 16384}
DEFAULT_MAX_TOKENS = 4096
STOP = {"end_turn": "end", "stop_sequence": "end", "pause_turn": "end", "max_tokens": "max_tokens", "tool_use": "tool_call", "refusal": "refusal"}
EPHEMERAL = {"type": "ephemeral"}


def _blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for b in blocks:
        kind = b["type"]
        if kind == "text":
            out.append({"type": "text", "text": b["text"]})
        elif kind == "image":
            out.append({"type": "image", "source": {"type": "base64", "media_type": b["media_type"], "data": b["data"]}})
        elif kind == "tool_call":
            out.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": b["arguments"]})
        else:
            out.append({"type": "tool_result", "tool_use_id": b["id"], "content": b["text"], "is_error": b["is_error"]})
    return out


def _thinking(state: str) -> list[dict[str, Any]]:
    try:
        blocks = json.loads(state)
    except ValueError:
        blocks = None
    if not isinstance(blocks, list) or not all(isinstance(b, dict) for b in blocks):
        raise GatewayError(422, "invalid_reasoning_state", "reasoning_state is not a value this gateway returned.")
    return blocks


def message_params(request: ChatRequest, model: str, default_max: int) -> dict[str, Any]:
    messages = []
    for m in request.messages:
        content = _blocks(m["content"])
        if m["role"] == "assistant" and m.get("reasoning_state"):
            content = _thinking(m["reasoning_state"]) + content
        messages.append({"role": "assistant" if m["role"] == "assistant" else "user", "content": content})
    params: dict[str, Any] = {"model": request.model or model, "max_tokens": request.max_tokens or default_max, "messages": messages}
    if request.system:
        params["system"] = [{"type": "text", "text": request.system, "cache_control": EPHEMERAL}] if request.cache else request.system
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in request.tools]
    if request.schema:
        tools = [{"name": request.schema["name"], "description": "Reply with this structure.", "input_schema": request.schema["schema"]}]
        params["tool_choice"] = {"type": "tool", "name": request.schema["name"]}
    elif tools:
        choice = request.tool_choice
        params["tool_choice"] = ({"type": "auto"} if choice == "auto" else {"type": "any"} if choice == "required"
                                 else {"type": "none"} if choice == "none" else {"type": "tool", "name": choice["name"]})
    if tools:
        if request.cache:
            tools[-1]["cache_control"] = EPHEMERAL
        params["tools"] = tools
    if request.cache and messages:
        messages[-1]["content"][-1]["cache_control"] = EPHEMERAL
    if request.reasoning:
        budget = request.reasoning["budget_tokens"] or BUDGETS[request.reasoning["effort"]]
        if request.max_tokens is None:
            params["max_tokens"] = max(default_max, budget + 1)
        params["thinking"] = {"type": "enabled", "budget_tokens": budget}  # Anthropic allows no temperature here
    elif request.temperature is not None:
        params["temperature"] = request.temperature
    return params


def build_result(body: dict[str, Any], schema_name: str | None = None) -> ChatResult:
    if body.get("stop_reason") not in STOP or not isinstance(body.get("content"), list):
        raise truncated()
    content, thoughts, state = [], [], []
    for b in body.get("content") or []:
        kind = b.get("type")
        if kind == "text":
            content.append({"type": "text", "text": b.get("text") or ""})
        elif kind == "tool_use":
            if schema_name and b.get("name") == schema_name:
                content.append({"type": "text", "text": json.dumps(b.get("input") or {})})
            else:
                content.append({"type": "tool_call", "id": b["id"], "name": b["name"], "arguments": b.get("input") or {}})
        elif kind == "thinking":
            thoughts.append(b.get("thinking") or "")
            state.append({"type": "thinking", "thinking": b.get("thinking") or "", "signature": b.get("signature") or ""})
        elif kind == "redacted_thinking":
            state.append({"type": "redacted_thinking", "data": b.get("data") or ""})
    stop = STOP.get(body.get("stop_reason"), "end")
    if schema_name and stop == "tool_call":
        stop = "end"
    u = body.get("usage") or {}
    cached = u.get("cache_read_input_tokens") or 0
    created = u.get("cache_creation_input_tokens") or 0
    usage = {"input_tokens": (u.get("input_tokens") or 0) + cached + created, "output_tokens": u.get("output_tokens") or 0,
             "cached_input_tokens": cached, "reasoning_tokens": 0}
    return ChatResult(content, stop, usage, str(body.get("model") or ""), "".join(thoughts) or None, json.dumps(state) if state else None)


class AnthropicGateway(BaseGateway):
    provider = "anthropic"

    def __init__(self, gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(gateway_id, entry, transport)
        auth = entry.get("auth", "key")
        options = {"http_client": sdk_client(self.http, self.timeout), "max_retries": 0}
        if auth == "bedrock":
            self.client = AsyncAnthropicBedrock(aws_region=entry["aws_region"], aws_access_key=entry["aws_access_key_id"],
                                                aws_secret_key=entry["aws_secret_access_key"], **options)
        elif auth == "vertex":
            self.client = AsyncAnthropicVertex(project_id=entry["project_id"], region=entry["region"], **options)
        else:
            self.client = AsyncAnthropic(api_key=entry["api_key"], base_url=entry.get("base_url"), default_headers={"x-api-key": entry["api_key"]}, **options)
        self.default_max = int(entry.get("default_max_tokens", DEFAULT_MAX_TOKENS))

    def validate(self, request: ChatRequest) -> None:
        if request.schema and request.reasoning:
            raise GatewayError(422, "schema_with_reasoning", "Anthropic cannot force a structured reply while it reasons. Send one of them.")
        if request.reasoning:
            budget = request.reasoning["budget_tokens"] or BUDGETS[request.reasoning["effort"]]
            if budget < 1024 or (request.max_tokens is not None and request.max_tokens <= budget):
                raise GatewayError(422, "invalid_reasoning_budget", "Anthropic requires a thinking budget of at least 1024 below max_tokens.")

    def _params(self, request: ChatRequest) -> dict[str, Any]:
        params = message_params(request, self.model, self.default_max)
        # Current SDK removed temperature from the signature; compatible providers still accept it.
        if "temperature" in params:
            params["extra_body"] = {"temperature": params.pop("temperature")}
        return params

    async def complete(self, request: ChatRequest) -> ChatResult:
        async with self.guard():
            message = await self.client.messages.create(**self._params(request))
            return build_result(message.model_dump(), request.schema and request.schema["name"])

    async def stream(self, request: ChatRequest) -> AsyncIterator[tuple]:
        schema_name = request.schema and request.schema["name"]
        blocks: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        meta: dict[str, Any] = {"model": "", "stop_reason": None}
        finished = False
        async with self.guard():
            stream = await self.client.messages.create(**self._params(request), stream=True)
            async with stream:
                async for event in stream:
                    kind = event.type
                    if kind == "message_start":
                        usage.update(event.message.usage.model_dump())
                        meta["model"] = event.message.model
                    elif kind == "content_block_start":
                        block = event.content_block.model_dump()
                        block["_json"] = ""
                        blocks[event.index] = block
                        if block["type"] == "tool_use" and block["name"] != schema_name:
                            yield "tool_call", block["id"], block["name"], ""
                    elif kind == "content_block_delta":
                        block, delta = blocks[event.index], event.delta
                        if delta.type == "text_delta":
                            block["text"] = (block.get("text") or "") + delta.text
                            yield "text", delta.text
                        elif delta.type == "thinking_delta":
                            block["thinking"] = (block.get("thinking") or "") + delta.thinking
                            yield "reasoning", delta.thinking
                        elif delta.type == "signature_delta":
                            block["signature"] = (block.get("signature") or "") + delta.signature
                        elif delta.type == "input_json_delta":
                            block["_json"] += delta.partial_json
                            yield (("text", delta.partial_json) if block["name"] == schema_name
                                   else ("tool_call", block["id"], block["name"], delta.partial_json))
                    elif kind == "message_delta":
                        meta["stop_reason"] = event.delta.stop_reason
                        usage.update({k: v for k, v in event.usage.model_dump().items() if v is not None})
                    elif kind == "message_stop":
                        finished = True
            if not finished:
                raise truncated()
        async with self.guard():
            content = []
            for index in sorted(blocks):
                block = dict(blocks[index])
                if block["type"] == "tool_use":
                    block["input"] = json.loads(block.pop("_json") or "{}")
                content.append(block)
            yield "done", build_result({"content": content, "stop_reason": meta["stop_reason"], "usage": usage, "model": meta["model"]}, schema_name)

    async def models(self) -> list[str]:
        if self.entry.get("auth", "key") != "key":  # Bedrock and Vertex have no model list
            return await super().models()
        async with self.guard():
            page = await self.client.models.list(limit=1000)
        return sorted({str(item.id) for item in page.data})

    async def probe(self) -> str:
        if self.entry.get("auth", "key") == "key":
            try:
                async with self.guard():
                    await self.client.models.list(limit=1)
                return "The provider accepted the credentials."
            except GatewayError as error:
                if error.code != "gateway_refused":
                    raise
        # Bedrock and Vertex have no model list, and some Anthropic-compatible gateways have none either: ask for one token
        async with self.guard():
            await self.client.messages.create(model=self.model, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        return "The provider accepted the credentials."
