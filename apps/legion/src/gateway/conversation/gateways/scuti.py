"""Provider `scuti`: a CNV model service (CNV_MiniCPM52B_Model, CNV_BitNet2B_Model, CNV_LFM3_Model, CNV_SparkX26_Model)
through POST /v1/chat. A service refuses fields it does not support with 422; that refusal goes to the caller."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from src.gateway.conversation.contract import ChatRequest, ChatResult
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.failure import scrub, upstream_error
from src.gateway.conversation.gateways.base import BaseGateway, truncated

NAME = "The model service"
FINISH = {"stop": "end", "tool_calls": "tool_call", "length": "max_tokens"}


def _user_message(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "user", "content": "\n".join(b["text"] for b in blocks if b["type"] == "text")}
    images = [b["data"] for b in blocks if b["type"] == "image"]
    if images:
        out["images"] = images  # a guess (Ollama style): no CNV service documents image input yet
    return out


def chat_body(entry: dict[str, Any], request: ChatRequest, can_think: bool, stream: bool) -> dict[str, Any]:
    names = {b["id"]: b["name"] for m in request.messages for b in m["content"] if b["type"] == "tool_call"}
    messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}] if request.system else []
    for m in request.messages:
        blocks = m["content"]
        if m["role"] == "tool":
            for b in blocks:
                row: dict[str, Any] = {"role": "tool", "content": b["text"]}
                if b["id"] in names:
                    row["tool_name"] = names[b["id"]]
                messages.append(row)
        elif m["role"] == "assistant":
            out: dict[str, Any] = {"role": "assistant", "content": "".join(b["text"] for b in blocks if b["type"] == "text")}
            calls = [{"id": b["id"], "name": b["name"], "arguments": b["arguments"]} for b in blocks if b["type"] == "tool_call"]
            if calls:
                out["tool_calls"] = calls
            messages.append(out)
        else:
            messages.append(_user_message(blocks))
    body: dict[str, Any] = {"messages": messages}
    if request.tools:
        body["tools"] = request.tools
    if request.schema:
        body["schema"] = request.schema["schema"]
    if can_think:
        body["thinking"] = bool(request.reasoning)
    elif request.reasoning:
        body["thinking"] = True  # the caller asked: the service answers 422 if it cannot
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.max_tokens:
        body["max_tokens"] = request.max_tokens
    if entry.get("project"):
        body["project"] = entry["project"]
    if stream:
        body["stream"] = True
    return body


def _result(body: dict[str, Any]) -> ChatResult:
    if not isinstance(body, dict) or body.get("finish_reason") not in FINISH:
        raise truncated()
    content = [{"type": "text", "text": body["content"]}] if body.get("content") else []
    for index, call in enumerate(body.get("tool_calls") or []):
        content.append({"type": "tool_call", "id": call.get("id") or f"call_{index}", "name": call.get("name") or "",
                        "arguments": call.get("arguments") or {}})
    u = body.get("usage") or {}
    return ChatResult(content, FINISH.get(body.get("finish_reason"), "end"),
                      {"input_tokens": u.get("input_tokens") or 0, "output_tokens": u.get("output_tokens") or 0,
                       "cached_input_tokens": 0, "reasoning_tokens": 0},
                      str(body.get("model") or ""), body.get("thinking") or None)


class ScutiGateway(BaseGateway):
    provider = "scuti"
    defaults = {"streams": True, "images": False, "tools": False, "reasoning": False, "schema": False, "audio": False}
    forwards_images = True

    def validate(self, request: ChatRequest) -> None:
        if request.model:
            raise GatewayError(422, "model_unsupported", "A model service runs one model; leave model out.")
        if request.tool_choice not in (None, "auto"):
            raise GatewayError(422, "tool_choice_unsupported", "This model service supports only automatic tool choice.")

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self.entry["token"]} if self.entry.get("token") else {}

    def _failure(self, status: int, text: str, headers: httpx.Headers) -> GatewayError:
        try:
            detail = json.loads(text).get("detail", text)
        except (ValueError, AttributeError):
            detail = text
        return upstream_error(status, detail if isinstance(detail, str) else json.dumps(detail), headers.get("retry-after"), self.secrets)

    def _body(self, request: ChatRequest, stream: bool) -> dict[str, Any]:
        return chat_body(self.entry, request, self.can("reasoning"), stream)

    async def complete(self, request: ChatRequest) -> ChatResult:
        async with self.guard():
            reply = await self.http.post(f"{self.entry['url']}/v1/chat", json=self._body(request, False), headers=self._headers())
            if reply.status_code >= 400:
                raise self._failure(reply.status_code, reply.text, reply.headers)
            try:
                body = reply.json()
            except ValueError:
                body = None
            if not isinstance(body, dict):
                raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.", kind="unavailable")
            return _result(body)

    async def stream(self, request: ChatRequest) -> AsyncIterator[tuple]:
        async with self.guard():
            async with self.http.stream("POST", f"{self.entry['url']}/v1/chat", json=self._body(request, True), headers=self._headers()) as reply:
                if reply.status_code >= 400:
                    raise self._failure(reply.status_code, (await reply.aread()).decode("utf-8", "replace"), reply.headers)
                async for line in reply.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        raise GatewayError(502, "gateway_bad_reply", f"{NAME} sent an unusable reply.", kind="unavailable") from None
                    kind = item.get("type") if isinstance(item, dict) else None
                    if kind == "content":
                        yield "text", item.get("text") or ""
                    elif kind == "thinking":
                        yield "reasoning", item.get("text") or ""
                    elif kind == "done":
                        result = _result(item)
                        for block in result.content:
                            if block["type"] == "tool_call":
                                yield "tool_call", block["id"], block["name"], json.dumps(block["arguments"])
                        yield "done", result
                        return
                    elif kind == "error":
                        status = item.get("status", 502)
                        status = status if isinstance(status, int) and 400 <= status <= 599 else 502
                        raise upstream_error(status, str(item.get("message") or item.get("detail") or f"{NAME} stopped answering."),
                                             secrets=self.secrets)
                raise truncated(NAME)

    async def probe(self) -> str:
        async with self.guard():
            reply = await self.http.get(f"{self.entry['url']}/health", timeout=10.0)
            if reply.status_code >= 400:
                raise self._failure(reply.status_code, reply.text, reply.headers)
            if reply.json().get("ready") is False:
                raise GatewayError(503, "gateway_not_ready", f"{NAME} is running but not ready (its model is not loaded).")
        return "The model service is reachable and ready."
