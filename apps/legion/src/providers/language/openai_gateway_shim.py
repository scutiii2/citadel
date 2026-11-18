"""The slice of the OpenAI SDK that openai_provider.py uses, served by
ConversationGateway.

The provider's tool loop builds Responses-API requests and reads
Responses-API replies. This module translates both ways, so the loop stays
as it is while the SDK and the provider keys leave Legion. Same idea as
anthropic_gateway_shim.py; only the wire shapes differ.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, AsyncIterator

from src.providers.gateway_client import ConversationGatewayClient, GatewayCallError

_EMPTY_SCHEMA = {"type": "object", "properties": {}}
_TEXT_PARTS = {"text", "input_text", "output_text"}


class _Item(SimpleNamespace):
    """One output item. `model_dump` is what the provider calls to resend it as input."""

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return dict(vars(self))


def _get(item: Any, key: str) -> Any:
    """A field of an input item, which is a dict we built or an object from a reply."""
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def _text(content: Any) -> str:
    """The text of a message's content: a string, or a list of text parts."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for part in content or []:
        if _get(part, "type") not in _TEXT_PARTS:
            raise ValueError(f"Unsupported content part: {_get(part, 'type')}")
        parts.append(_get(part, "text") or "")
    return "".join(parts)


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _messages(items: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    """The system text and the gateway messages for a Responses `input` list.
    One model round arrives as separate items (reasoning, message, function calls);
    the gateway wants them as one assistant message, and tool outputs as one `tool` message."""
    system: list[str] = []
    out: list[dict[str, Any]] = []
    turn: dict[str, Any] | None = None  # the assistant message being collected
    results: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal turn, results
        if turn is not None:
            out.append(turn)
        if results:
            out.append({"role": "tool", "content": results})
        turn, results = None, []

    def assistant() -> dict[str, Any]:
        nonlocal turn
        if results:
            flush()
        if turn is None:
            turn = {"role": "assistant", "content": []}
        return turn

    for item in items:
        kind, role = _get(item, "type"), _get(item, "role")
        if kind == "reasoning":
            if _get(item, "state"):
                assistant()["reasoning_state"] = _get(item, "state")
        elif kind == "function_call":
            assistant()["content"].append({"type": "tool_call", "id": _get(item, "call_id"),
                                           "name": _get(item, "name"), "arguments": _arguments(_get(item, "arguments"))})
        elif kind == "function_call_output":
            results.append({"type": "tool_result", "id": _get(item, "call_id"),
                            "text": str(_get(item, "output") or ""), "is_error": False})
        elif role == "assistant" and kind == "message":
            text = _text(_get(item, "content"))
            if text:
                assistant()["content"].append({"type": "text", "text": text})
        elif role == "system":
            system.append(_text(_get(item, "content")))
        elif role in ("user", "assistant"):
            flush()
            out.append({"role": role, "content": _text(_get(item, "content"))})
        else:
            raise ValueError(f"Unsupported input item: {kind or role}")
    flush()
    return "\n\n".join(part for part in system if part), out


def request_body(gateway: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """The gateway chat body for one `responses.stream(...)` / `responses.create(...)` call."""
    system, messages = _messages(kwargs["input"])
    body: dict[str, Any] = {"gateway": gateway, "model": kwargs["model"], "max_tokens": kwargs["max_output_tokens"]}
    if system:
        body["system"] = system
    body["messages"] = messages
    if kwargs.get("tools"):
        body["tools"] = [{"name": tool["name"], "description": tool.get("description") or "",
                          "parameters": tool.get("parameters") or _EMPTY_SCHEMA} for tool in kwargs["tools"]]
    if kwargs.get("temperature") is not None:
        body["temperature"] = kwargs["temperature"]
    effort = (kwargs.get("reasoning") or {}).get("effort")
    if effort:
        body["reasoning"] = {"effort": effort}
    return body


def response(reply: dict[str, Any]) -> SimpleNamespace:
    """A gateway reply (the `done` event or a plain response) as a Responses-shaped object.
    `reasoning_state` rides along as a `reasoning` item: the loop resends it on the next
    round and drops it when it switches gateway, as it did with SDK reasoning items."""
    output: list[_Item] = []
    if reply.get("reasoning_state"):
        output.append(_Item(type="reasoning", state=reply["reasoning_state"]))
    texts: list[str] = []
    for block in reply.get("content") or []:
        if block.get("type") == "text" and block.get("text"):
            texts.append(block["text"])
            output.append(_Item(type="message", role="assistant",
                                content=[{"type": "output_text", "text": block["text"]}]))
        elif block.get("type") == "tool_call":
            output.append(_Item(type="function_call", call_id=block["id"], name=block["name"],
                                arguments=json.dumps(block.get("arguments") or {})))
    usage = reply.get("usage") or {}
    sent, written = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    return SimpleNamespace(
        output=output, output_text="".join(texts),
        usage=SimpleNamespace(input_tokens=sent, output_tokens=written, total_tokens=sent + written),
    )


class _Stream:
    """One streamed round: Responses-style delta events, then the whole response."""

    def __init__(self, events: AsyncIterator[dict[str, Any]]) -> None:
        self._events = events
        self._done: dict[str, Any] | None = None

    async def __aiter__(self) -> AsyncIterator[SimpleNamespace]:
        async for event in self._events:
            kind = event.get("type")
            if kind == "done":
                self._done = event
            elif kind in ("text", "reasoning") and event.get("delta"):
                name = "response.output_text.delta" if kind == "text" else "response.reasoning_text.delta"
                yield SimpleNamespace(type=name, delta=event["delta"])

    async def get_final_response(self) -> SimpleNamespace:
        if self._done is None:
            raise GatewayCallError(502, "gateway_unavailable", "ConversationGateway ended the stream early.",
                                   kind="unavailable")
        return response(self._done)


class _StreamContext:
    def __init__(self, events: AsyncIterator[dict[str, Any]]) -> None:
        self._events = events

    async def __aenter__(self) -> _Stream:
        return _Stream(self._events)

    async def __aexit__(self, *_exc: Any) -> bool:
        await self._events.aclose()
        return False


class _InputTokens:
    async def count(self, **_kwargs: Any) -> Any:
        """The gateway has no token-count route; the caller settles for its estimate."""
        raise NotImplementedError("ConversationGateway does not count tokens")


class _Responses:
    def __init__(self, gateway: str, client: ConversationGatewayClient) -> None:
        self._gateway = gateway
        self._client = client
        self.input_tokens = _InputTokens()

    def stream(self, **kwargs: Any) -> _StreamContext:
        return _StreamContext(self._client.stream(request_body(self._gateway, kwargs)))

    def create(self, **kwargs: Any) -> SimpleNamespace:
        return response(self._client.chat_sync(request_body(self._gateway, kwargs)))


class GatewayShim:
    """Stands where an OpenAI SDK client stood, for one saved gateway."""

    def __init__(self, gateway: str, client: ConversationGatewayClient) -> None:
        self.responses = _Responses(gateway, client)
