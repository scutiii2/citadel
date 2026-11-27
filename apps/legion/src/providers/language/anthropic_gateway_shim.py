"""The slice of the Anthropic SDK that anthropic_provider.py uses, served by
ConversationGateway.

The provider's tool loop builds Anthropic-shaped requests and reads
Anthropic-shaped replies. This module translates both ways, so the loop and
its tests stay as they are while the SDK and the provider keys leave Legion.
Pure functions do the translation; the classes only carry the calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

from src.providers.gateway_client import ConversationGatewayClient, GatewayCallError

_STOP_REASONS = {"end": "end_turn", "tool_call": "tool_use"}
_EMPTY_SCHEMA = {"type": "object", "properties": {}}


def _get(block: Any, key: str) -> Any:
    """A field of a content block, which is a dict we built or an object from a reply."""
    return block.get(key) if isinstance(block, dict) else getattr(block, key, None)


def _has_cache_marker(blocks: Any) -> bool:
    return isinstance(blocks, list) and any(isinstance(block, dict) and "cache_control" in block for block in blocks)


def _messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Gateway messages, and whether any block carried a cache marker.
    Anthropic sends tool results inside a user message; the gateway has a `tool` role."""
    out: list[dict[str, Any]] = []
    cache = False
    for message in messages:
        role, content = message["role"], message.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        cache = cache or _has_cache_marker(content)
        blocks: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        state: str | None = None
        for block in content or []:
            kind = _get(block, "type")
            if kind == "text":
                if _get(block, "text"):
                    blocks.append({"type": "text", "text": _get(block, "text")})
            elif kind == "tool_use":
                blocks.append({"type": "tool_call", "id": _get(block, "id"), "name": _get(block, "name"),
                               "arguments": _get(block, "input") or {}})
            elif kind == "tool_result":
                results.append({"type": "tool_result", "id": _get(block, "tool_use_id"),
                                "text": str(_get(block, "content") or ""), "is_error": bool(_get(block, "is_error"))})
            elif kind == "thinking":
                state = _get(block, "state")
            elif kind in ("image", "audio"):
                source = _get(block, "source") or {}
                blocks.append({"type": kind, "media_type": source.get("media_type"), "data": source.get("data")})
            else:
                raise ValueError(f"Unsupported content block: {kind}")
        if results:
            out.append({"role": "tool", "content": results})
        if blocks or state:
            converted: dict[str, Any] = {"role": role, "content": blocks}
            if state:
                converted = {"role": role, "reasoning_state": state, "content": blocks}
            out.append(converted)
    return out, cache


def request_body(gateway: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """The gateway chat body for one `messages.stream(...)` / `messages.create(...)` call."""
    system = kwargs.get("system")
    cache = _has_cache_marker(system)
    if isinstance(system, list):
        system = "".join(block["text"] for block in system)
    raw_tools = kwargs.get("tools") or []
    cache = cache or _has_cache_marker(raw_tools)
    messages, marked = _messages(kwargs["messages"])
    body: dict[str, Any] = {"gateway": gateway, "model": kwargs["model"], "max_tokens": kwargs["max_tokens"]}
    if system:
        body["system"] = system
    body["messages"] = messages
    if raw_tools:
        body["tools"] = [{"name": tool["name"], "description": tool.get("description") or "",
                          "parameters": tool.get("input_schema") or _EMPTY_SCHEMA} for tool in raw_tools]
    if cache or marked:
        body["cache"] = True
    temperature = (kwargs.get("extra_body") or {}).get("temperature")
    if temperature is not None:
        body["temperature"] = temperature
    effort = (kwargs.get("output_config") or {}).get("effort")
    if effort:
        body["reasoning"] = {"effort": effort}
    return body


def response_message(reply: dict[str, Any]) -> SimpleNamespace:
    """A gateway reply (the `done` event or a plain response) as an Anthropic-shaped message.
    `reasoning_state` rides along as a `thinking` block: the loop sends it back on the next
    round and drops it when it switches gateway, exactly as it treats SDK thinking blocks."""
    content: list[SimpleNamespace] = []
    if reply.get("reasoning_state"):
        content.append(SimpleNamespace(type="thinking", state=reply["reasoning_state"]))
    for block in reply.get("content") or []:
        if block.get("type") == "text":
            content.append(SimpleNamespace(type="text", text=block.get("text") or ""))
        elif block.get("type") == "tool_call":
            content.append(SimpleNamespace(type="tool_use", id=block["id"], name=block["name"],
                                           input=block.get("arguments") or {}))
    usage = reply.get("usage") or {}
    cached = int(usage.get("cached_input_tokens") or 0)
    stop = reply.get("stop_reason") or "end"
    return SimpleNamespace(
        content=content,
        stop_reason=_STOP_REASONS.get(stop, stop),
        # The gateway's input count already includes cache reads and writes. The provider
        # adds the three counters back together, so the cached part is split out here.
        usage=SimpleNamespace(
            input_tokens=max(int(usage.get("input_tokens") or 0) - cached, 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_input_tokens=cached,
            cache_creation_input_tokens=0,
        ),
    )


class _Stream:
    """One streamed round: text chunks first, then the whole message."""

    def __init__(self, events: AsyncIterator[dict[str, Any]]) -> None:
        self._events = events
        self._done: dict[str, Any] | None = None
        self.text_stream = self._text()

    async def _text(self) -> AsyncIterator[str]:
        async for event in self._events:
            if event.get("type") == "text" and event.get("delta"):
                yield event["delta"]
            elif event.get("type") == "done":
                self._done = event

    async def get_final_message(self) -> SimpleNamespace:
        async for _chunk in self.text_stream:  # a caller that stopped reading early
            pass
        if self._done is None:
            raise GatewayCallError(502, "gateway_unavailable", "ConversationGateway ended the stream early.",
                                   kind="unavailable")
        return response_message(self._done)


class _StreamContext:
    def __init__(self, events: AsyncIterator[dict[str, Any]]) -> None:
        self._events = events

    async def __aenter__(self) -> _Stream:
        return _Stream(self._events)

    async def __aexit__(self, *_exc: Any) -> bool:
        await self._events.aclose()
        return False


class _Messages:
    def __init__(self, gateway: str, client: ConversationGatewayClient) -> None:
        self._gateway = gateway
        self._client = client

    def stream(self, **kwargs: Any) -> _StreamContext:
        return _StreamContext(self._client.stream(request_body(self._gateway, kwargs)))

    def create(self, **kwargs: Any) -> SimpleNamespace:
        return response_message(self._client.chat_sync(request_body(self._gateway, kwargs)))

    async def count_tokens(self, **_kwargs: Any) -> Any:
        """The gateway has no token-count route; the caller settles for its estimate."""
        raise NotImplementedError("ConversationGateway does not count tokens")


class GatewayShim:
    """Stands where an Anthropic SDK client stood, for one saved gateway."""

    def __init__(self, gateway: str, client: ConversationGatewayClient) -> None:
        self.messages = _Messages(gateway, client)
