"""Provider `openai`: OpenAI and every OpenAI-compatible server (Gemini, Groq, Together, Ollama, vLLM, ...) plus Azure.
`api: responses` uses the Responses API (GPT, Azure); `api: chat` uses Chat Completions (all compatible servers)."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
from openai import AsyncAzureOpenAI, AsyncOpenAI

from src.gateway.conversation.contract import ChatRequest, ChatResult
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.gateways.base import BaseGateway, truncated
from src.gateway.conversation.gateways.sdk_http import sdk_client

FINISH = {"stop": "end", "length": "max_tokens", "tool_calls": "tool_call", "function_call": "tool_call", "content_filter": "refusal"}


def _effort(reasoning: dict[str, Any]) -> str:
    if reasoning["effort"]:
        return reasoning["effort"]
    budget = reasoning["budget_tokens"]
    return "low" if budget <= 2048 else "medium" if budget <= 8192 else "high"


def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {"_raw": str(raw)}
    return value if isinstance(value, dict) else {"_raw": str(raw)}


def _data_url(block: dict[str, Any]) -> str:
    return f"data:{block['media_type']};base64,{block['data']}"


def _user_part(block: dict[str, Any]) -> dict[str, Any]:
    """One block of a user message for Chat Completions."""
    if block["type"] == "text":
        return {"type": "text", "text": block["text"]}
    if block["type"] == "audio":
        form = "wav" if block["media_type"] == "audio/wav" else "mp3"
        return {"type": "input_audio", "input_audio": {"data": block["data"], "format": form}}
    return {"type": "image_url", "image_url": {"url": _data_url(block)}}


def chat_params(request: ChatRequest, model: str, entry: dict[str, Any]) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}] if request.system else []
    for m in request.messages:
        blocks = m["content"]
        if m["role"] == "tool":
            messages += [{"role": "tool", "tool_call_id": b["id"], "content": b["text"]} for b in blocks]
        elif m["role"] == "assistant":
            text = "".join(b["text"] for b in blocks if b["type"] == "text")
            out: dict[str, Any] = {"role": "assistant", "content": text or None}
            calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["arguments"])}}
                     for b in blocks if b["type"] == "tool_call"]
            if calls:
                out["tool_calls"] = calls
            messages.append(out)
        else:
            parts = [_user_part(b) for b in blocks]
            messages.append({"role": "user", "content": parts[0]["text"] if len(parts) == 1 and parts[0]["type"] == "text" else parts})
    params: dict[str, Any] = {"model": request.model or model, "messages": messages}
    if request.tools:
        params["tools"] = [{"type": "function", "function": t} for t in request.tools]
        choice = request.tool_choice
        params["tool_choice"] = choice if isinstance(choice, str) else {"type": "function", "function": {"name": choice["name"]}}
    if request.schema:
        params["response_format"] = {"type": "json_schema", "json_schema": {
            "name": request.schema["name"], "schema": request.schema["schema"], "strict": request.schema["strict"]}}
    if request.reasoning:
        params["reasoning_effort"] = _effort(request.reasoning)
    elif request.temperature is not None:
        params["temperature"] = request.temperature
    if request.max_tokens:
        params[entry.get("max_tokens_param", "max_tokens")] = request.max_tokens
    return params


def _usage(u: dict[str, Any]) -> dict[str, int]:
    return {"input_tokens": u.get("prompt_tokens") or u.get("input_tokens") or 0,
            "output_tokens": u.get("completion_tokens") or u.get("output_tokens") or 0,
            "cached_input_tokens": ((u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}).get("cached_tokens")) or 0,
            "reasoning_tokens": ((u.get("completion_tokens_details") or u.get("output_tokens_details") or {}).get("reasoning_tokens")) or 0}


def chat_result(body: dict[str, Any]) -> ChatResult:
    if not body.get("choices") or body["choices"][0].get("finish_reason") not in FINISH:
        raise truncated()
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = [{"type": "text", "text": message["content"]}] if message.get("content") else []
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function") or {}
        content.append({"type": "tool_call", "id": call.get("id") or f"call_{index}", "name": function.get("name") or "",
                        "arguments": _args(function.get("arguments"))})
    stop = FINISH.get(choice.get("finish_reason"), "end")
    if message.get("refusal"):
        stop = "refusal"
    return ChatResult(content, stop, _usage(body.get("usage") or {}), str(body.get("model") or ""),
                      message.get("reasoning_content") or message.get("reasoning") or None)


def responses_params(request: ChatRequest, model: str, entry: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for m in request.messages:
        blocks = m["content"]
        if m["role"] == "tool":
            items += [{"type": "function_call_output", "call_id": b["id"], "output": b["text"]} for b in blocks]
        elif m["role"] == "assistant":
            text = "".join(b["text"] for b in blocks if b["type"] == "text")
            if text:
                items.append({"role": "assistant", "content": text})
            items += [{"type": "function_call", "call_id": b["id"], "name": b["name"], "arguments": json.dumps(b["arguments"])}
                      for b in blocks if b["type"] == "tool_call"]
        else:
            items.append({"role": "user", "content": [{"type": "input_text", "text": b["text"]} if b["type"] == "text"
                                                       else {"type": "input_image", "image_url": _data_url(b)} for b in blocks]})
    params: dict[str, Any] = {"model": request.model or model, "input": items}
    if request.system:
        params["instructions"] = request.system
    if request.tools:
        params["tools"] = [{"type": "function", **t} for t in request.tools]
        choice = request.tool_choice
        params["tool_choice"] = choice if isinstance(choice, str) else {"type": "function", "name": choice["name"]}
    if request.schema:
        params["text"] = {"format": {"type": "json_schema", "name": request.schema["name"], "schema": request.schema["schema"],
                                     "strict": request.schema["strict"]}}
    if request.reasoning:
        params["reasoning"] = {"effort": _effort(request.reasoning), "summary": "auto"}
    elif request.temperature is not None:
        params["temperature"] = request.temperature
    if request.max_tokens:
        params["max_output_tokens"] = request.max_tokens
    return params


def responses_result(body: dict[str, Any]) -> ChatResult:
    if body.get("status") not in ("completed", "incomplete", "failed") or not isinstance(body.get("output"), list):
        raise truncated()
    content, thoughts = [], []
    refused = False
    for item in body.get("output") or []:
        kind = item.get("type")
        if kind == "message":
            content += [{"type": "text", "text": part["text"]} for part in item.get("content") or [] if part.get("type") == "output_text"]
            refused = refused or any(part.get("type") == "refusal" for part in item.get("content") or [])
        elif kind == "function_call":
            content.append({"type": "tool_call", "id": item.get("call_id") or item.get("id"), "name": item.get("name") or "",
                            "arguments": _args(item.get("arguments"))})
        elif kind == "reasoning":
            thoughts += [s.get("text") or "" for s in item.get("summary") or []]
    reason = (body.get("incomplete_details") or {}).get("reason")
    stop = ("error" if body.get("status") == "failed" else "refusal" if refused else
            "tool_call" if any(b["type"] == "tool_call" for b in content) else
            "max_tokens" if body.get("status") == "incomplete" and reason == "max_output_tokens" else
            "refusal" if body.get("status") == "incomplete" and reason == "content_filter" else "end")
    return ChatResult(content, stop, _usage(body.get("usage") or {}), str(body.get("model") or ""), "\n".join(t for t in thoughts if t) or None)


class OpenAIGateway(BaseGateway):
    provider = "openai"

    def sends_audio(self, entry: dict[str, Any]) -> bool:
        return entry.get("api", "chat") == "chat"

    def __init__(self, gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(gateway_id, entry, transport)
        self.api = entry.get("api", "chat")
        options = {"http_client": sdk_client(self.http, self.timeout), "max_retries": 0}
        if entry.get("auth") == "azure":
            self.client = AsyncAzureOpenAI(azure_endpoint=entry["azure_endpoint"], api_version=entry["api_version"],
                                           api_key=entry["api_key"], **options)
        else:  # a local server (Ollama, vLLM) may need no key; the SDK wants a non-empty one
            self.client = AsyncOpenAI(api_key=entry.get("api_key") or "none", base_url=entry.get("base_url"), **options)

    async def complete(self, request: ChatRequest) -> ChatResult:
        async with self.guard():
            if self.api == "responses":
                response = await self.client.responses.create(**responses_params(request, self.model, self.entry))
                return responses_result(response.model_dump())
            completion = await self.client.chat.completions.create(**chat_params(request, self.model, self.entry))
            return chat_result(completion.model_dump())

    def stream(self, request: ChatRequest) -> AsyncIterator[tuple]:
        return self._responses_stream(request) if self.api == "responses" else self._chat_stream(request)

    async def _chat_stream(self, request: ChatRequest) -> AsyncIterator[tuple]:
        params = chat_params(request, self.model, self.entry)
        if self.entry.get("stream_usage", True):
            params["stream_options"] = {"include_usage": True}
        text: list[str] = []
        thoughts: list[str] = []
        refusals: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        usage: dict[str, Any] = {}
        finish = None
        model = ""
        async with self.guard():
            stream = await self.client.chat.completions.create(**params, stream=True)
            async with stream:
                async for chunk in stream:
                    data = chunk.model_dump()
                    model = data.get("model") or model
                    usage = data.get("usage") or usage
                    for choice in data.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text.append(delta["content"])
                            yield "text", delta["content"]
                        thought = delta.get("reasoning_content") or delta.get("reasoning")
                        if thought:
                            thoughts.append(thought)
                            yield "reasoning", thought
                        if delta.get("refusal"):
                            refusals.append(delta["refusal"])
                        for piece in delta.get("tool_calls") or []:
                            slot = calls.setdefault(piece.get("index") or 0, {"id": "", "name": "", "arguments": ""})
                            function = piece.get("function") or {}
                            slot["id"] = piece.get("id") or slot["id"]
                            slot["name"] = function.get("name") or slot["name"]
                            slot["arguments"] += function.get("arguments") or ""
                            yield "tool_call", slot["id"], slot["name"], function.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
            if finish is None:
                raise truncated()
        message: dict[str, Any] = {"content": "".join(text) or None, "reasoning_content": "".join(thoughts) or None,
                                   "refusal": "".join(refusals) or None,
                                   "tool_calls": [{"id": c["id"], "function": {"name": c["name"], "arguments": c["arguments"]}}
                                                  for _, c in sorted(calls.items())]}
        yield "done", chat_result({"choices": [{"message": message, "finish_reason": finish}], "usage": usage, "model": model})

    async def _responses_stream(self, request: ChatRequest) -> AsyncIterator[tuple]:
        params = responses_params(request, self.model, self.entry)
        calls: dict[str, tuple[str, str]] = {}
        final = None
        async with self.guard():
            stream = await self.client.responses.create(**params, stream=True)
            async with stream:
                async for event in stream:
                    kind = event.type
                    if kind == "response.output_text.delta":
                        yield "text", event.delta
                    elif kind == "response.reasoning_summary_text.delta":
                        yield "reasoning", event.delta
                    elif kind == "response.output_item.added" and event.item.type == "function_call":
                        calls[event.item.id] = (event.item.call_id, event.item.name)
                        yield "tool_call", event.item.call_id, event.item.name, ""
                    elif kind == "response.function_call_arguments.delta":
                        call_id, name = calls.get(event.item_id, ("", ""))
                        yield "tool_call", call_id, name, event.delta
                    elif kind in ("response.completed", "response.incomplete"):
                        final = event.response.model_dump()
                    elif kind in ("response.failed", "error"):
                        raise GatewayError(502, "gateway_unavailable", "The model service stopped answering.", kind="unavailable")
            if final is None:
                raise truncated()
        yield "done", responses_result(final)

    async def probe(self) -> str:
        if self.entry.get("auth") != "azure":
            try:
                async with self.guard():
                    await self.client.models.list()
                return "The provider accepted the credentials."
            except GatewayError as error:
                if error.code != "gateway_refused":
                    raise
        # Azure lists deployments differently, and some providers have no model list (Perplexity): ask for a few tokens
        await self.complete_ping()
        return "The provider accepted the credentials."

    async def models(self) -> list[str]:
        if self.entry.get("auth") == "azure":  # Azure lists deployments through another API
            return await super().models()
        async with self.guard():
            page = await self.client.models.list()
        return sorted({str(item.id) for item in page.data})[:1000]

    async def complete_ping(self) -> None:
        from src.gateway.conversation.contract import ChatRequest as Request
        ping = Request(self.id, None, None, [{"role": "user", "content": [{"type": "text", "text": "ping"}]}], [], None, None, None,
                       16, None, False, False)
        await self.complete(ping)
