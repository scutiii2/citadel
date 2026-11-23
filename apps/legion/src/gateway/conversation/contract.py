"""The chat request: validated and normalized once, so adapters never re-check shapes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.gateway.conversation.errors import GatewayError

TIERS = ("light", "standard", "heavy", "extreme")
TOP = {"gateway", "model", "tier", "system", "messages", "tools", "tool_choice", "schema", "reasoning", "max_tokens",
       "temperature", "cache", "stream"}
BLOCKS = {  # role -> block type -> allowed keys
    "user": {"text": {"type", "text"}, "image": {"type", "media_type", "data"}},
    "assistant": {"text": {"type", "text"}, "tool_call": {"type", "id", "name", "arguments"}},
    "tool": {"tool_result": {"type", "id", "text", "is_error"}},
}
MEDIA = {"image/png", "image/jpeg", "image/webp", "image/gif"}
EFFORTS = ("low", "medium", "high")
NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
MAX_STATE = 1_000_000


@dataclass(frozen=True)
class Limits:
    max_messages: int
    max_text: int
    max_tools: int
    max_images: int
    max_image_bytes: int

    @classmethod
    def from_settings(cls, s: Any) -> "Limits":
        return cls(s.max_messages, s.max_text, s.max_tools, s.max_images, s.max_image_mb * 1024 * 1024)


@dataclass(frozen=True)
class ChatRequest:
    gateway: str
    model: str | None
    system: str | None
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    tool_choice: Any
    schema: dict[str, Any] | None
    reasoning: dict[str, Any] | None
    max_tokens: int | None
    temperature: float | None
    cache: bool
    stream: bool
    tier: str | None = None  # light, standard, heavy or extreme: the gateway's saved model for that tier

    @property
    def uses(self) -> set[str]:
        used: set[str] = set()
        types = {b["type"] for m in self.messages for b in m["content"]}
        if "image" in types:
            used.add("images")
        if self.tools or types & {"tool_call", "tool_result"}:
            used.add("tools")
        if self.reasoning:
            used.add("reasoning")
        if self.schema:
            used.add("schema")
        return used


@dataclass
class ChatResult:
    content: list[dict[str, Any]]
    stop_reason: str = "end"
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    reasoning: str | None = None
    reasoning_state: str | None = None


def bad(message: str) -> GatewayError:
    return GatewayError(422, "invalid_request", f"Invalid chat request: {message}")


def _text(value: Any, label: str, limit: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not empty):
        raise bad(f"{label} must be text" + ("" if empty else " and not empty") + ".")
    if len(value) > limit:
        raise bad(f"{label} is longer than {limit} characters.")
    return value


def _blocks(role: str, content: Any, limits: Limits, images: list[int]) -> list[dict[str, Any]]:
    if isinstance(content, str) and role != "tool":
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list) or not content:
        raise bad(f"the content of a {role} message must be text or a list of blocks.")
    out = []
    for block in content:
        kind = block.get("type") if isinstance(block, dict) else None
        allowed = BLOCKS[role].get(kind) if isinstance(kind, str) else None
        if allowed is None:
            raise bad(f"a {role} message cannot hold a '{kind}' block.")
        if set(block) - allowed:
            raise bad(f"unexpected field in a {kind} block.")
        if kind == "text":
            out.append({"type": "text", "text": _text(block.get("text"), "text", limits.max_text)})
        elif kind == "image":
            if not isinstance(block.get("media_type"), str) or block["media_type"] not in MEDIA:
                raise bad("an image media_type must be image/png, image/jpeg, image/webp or image/gif.")
            data = _text(block.get("data"), "image data", limits.max_image_bytes * 4 // 3 + 4)
            # shortcut: size is estimated from the base64 length and the base64 is not decoded here; upstream rejects bad data.
            if len(data) * 3 // 4 - min(2, len(data) - len(data.rstrip("="))) > limits.max_image_bytes:
                raise bad("an image is larger than the limit.")
            images[0] += 1
            out.append({"type": "image", "media_type": block["media_type"], "data": data})
        elif kind == "tool_call":
            name = block.get("name")
            if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(block.get("arguments"), dict):
                raise bad("a tool_call needs a valid name and an arguments object.")
            out.append({"type": "tool_call", "id": _text(block.get("id"), "tool_call id", 200), "name": name, "arguments": block["arguments"]})
        else:
            is_error = block.get("is_error", False)
            if not isinstance(is_error, bool):
                raise bad("is_error must be true or false.")
            out.append({"type": "tool_result", "id": _text(block.get("id"), "tool_result id", 200),
                        "text": _text(block.get("text", ""), "tool_result text", limits.max_text, empty=True), "is_error": is_error})
    return out


def _tools(value: Any, limits: Limits) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limits.max_tools:
        raise bad(f"tools must be a list of at most {limits.max_tools}.")
    out, seen = [], set()
    for tool in value:
        if not isinstance(tool, dict) or set(tool) - {"name", "description", "parameters"}:
            raise bad("a tool has only name, description and parameters.")
        name = tool.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in seen:
            raise bad("tool names must be unique and match [A-Za-z0-9_.-]{1,64}.")
        seen.add(name)
        parameters = tool.get("parameters", {"type": "object", "properties": {}})
        if not isinstance(parameters, dict):
            raise bad("tool parameters must be a JSON schema object.")
        out.append({"name": name, "description": _text(tool.get("description", ""), "tool description", 4000, empty=True), "parameters": parameters})
    return out


def parse_request(data: Any, limits: Limits) -> ChatRequest:
    if not isinstance(data, dict):
        raise bad("the body must be a JSON object.")
    if set(data) - TOP:
        raise bad(f"unexpected field '{sorted(set(data) - TOP)[0]}'.")
    gateway = data.get("gateway")
    if not isinstance(gateway, str) or not gateway:
        raise bad("gateway is required.")
    raw = data.get("messages")
    if not isinstance(raw, list) or not 1 <= len(raw) <= limits.max_messages:
        raise bad(f"messages must be a list of 1 to {limits.max_messages}.")
    images, messages = [0], []
    for item in raw:
        if (not isinstance(item, dict) or set(item) - {"role", "content", "reasoning_state"}
                or not isinstance(item.get("role"), str) or item["role"] not in BLOCKS):
            raise bad("each message has a role (user, assistant or tool), content and for assistants an optional reasoning_state.")
        message = {"role": item["role"], "content": _blocks(item["role"], item.get("content"), limits, images)}
        if "reasoning_state" in item:
            if item["role"] != "assistant":
                raise bad("reasoning_state belongs on assistant messages.")
            message["reasoning_state"] = _text(item["reasoning_state"], "reasoning_state", MAX_STATE)
        messages.append(message)
    if images[0] > limits.max_images:
        raise bad(f"at most {limits.max_images} images.")
    tools = _tools(data.get("tools"), limits)
    choice = data.get("tool_choice")
    if choice is not None:
        names = {t["name"] for t in tools}
        valid = choice in ("auto", "none", "required") or (isinstance(choice, dict) and set(choice) == {"name"}
                and isinstance(choice["name"], str) and choice["name"] in names)
        if not tools or not valid:
            raise bad("tool_choice needs tools and must be auto, none, required or {\"name\": <a tool>}.")
    elif tools:
        choice = "auto"
    schema = data.get("schema")
    if schema is not None:
        if (not isinstance(schema, dict) or set(schema) - {"name", "schema", "strict"} or not isinstance(schema.get("name"), str)
                or not NAME.fullmatch(schema["name"]) or not isinstance(schema.get("schema"), dict)
                or not isinstance(schema.get("strict", False), bool)):
            raise bad("schema is {\"name\", \"schema\", \"strict\"?} with a JSON schema object.")
        if tools:
            raise bad("send either tools or a schema, not both.")
        schema = {"name": schema["name"], "schema": schema["schema"], "strict": schema.get("strict", False)}
    reasoning = data.get("reasoning")
    if reasoning is not None:
        if not isinstance(reasoning, dict) or set(reasoning) - {"effort", "budget_tokens"}:
            raise bad("reasoning is {\"effort\"?, \"budget_tokens\"?}.")
        effort, budget = reasoning.get("effort"), reasoning.get("budget_tokens")
        if effort is not None and effort not in EFFORTS:
            raise bad("reasoning effort must be low, medium or high.")
        if budget is not None and (isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 200000):
            raise bad("reasoning budget_tokens must be a whole number from 1 to 200000.")
        reasoning = {"effort": effort or (None if budget else "medium"), "budget_tokens": budget}
    max_tokens, temperature = data.get("max_tokens"), data.get("temperature")
    if max_tokens is not None and (isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 1_000_000):
        raise bad("max_tokens must be a whole number from 1 to 1000000.")
    if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2):
        raise bad("temperature must be a number from 0 to 2.")
    for key in ("cache", "stream"):
        if not isinstance(data.get(key, False), bool):
            raise bad(f"{key} must be true or false.")
    model = data.get("model")
    if model is not None:
        model = _text(model, "model", 200)
    tier = data.get("tier")
    if tier is not None:
        if tier not in TIERS:
            raise bad("tier must be light, standard, heavy or extreme.")
        if model is not None:
            raise bad("send either model or tier, not both.")
    system = data.get("system")
    if system is not None:
        system = _text(system, "system", limits.max_text)
    return ChatRequest(gateway, model, system, messages, tools, choice, schema, reasoning, max_tokens,
                       None if temperature is None else float(temperature), data.get("cache", False), data.get("stream", False), tier)
