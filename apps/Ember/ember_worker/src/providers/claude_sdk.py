"""The only module that imports claude_agent_sdk. It turns the SDK's messages into TurnEvents
and builds one client per turn; ClaudeProvider (claude.py) knows nothing about the SDK."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
)
from claude_agent_sdk.types import ToolUseBlock

try:
    from claude_agent_sdk import StreamEvent
except ImportError:  # older SDK layouts keep it in types
    from claude_agent_sdk.types import StreamEvent

from src.events import Failed, Finished, TextDelta, ToolCall, TurnEvent, TurnRequest, UsageReport
from src.providers.base import compose_prompt, summarize_tool
from src.providers.claude import CanUse

DECLINED = "The user declined this in Ember."


def translate_message(message: Any) -> list[TurnEvent]:
    """The events one SDK message stands for (usually none)."""
    if isinstance(message, StreamEvent):
        inner = message.event if isinstance(message.event, dict) else {}
        if inner.get("type") == "content_block_delta":
            delta = inner.get("delta") or {}
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                return [TextDelta(delta["text"])]
        return []
    if isinstance(message, AssistantMessage):
        if message.parent_tool_use_id is not None:
            return []
        return [
            ToolCall(block.name, summarize_tool(block.name, block.input))
            for block in message.content
            if isinstance(block, ToolUseBlock)
        ]
    if isinstance(message, ResultMessage):
        events: list[TurnEvent] = []
        usage = message.usage or {}
        if usage:
            events.append(UsageReport(int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0)))
        if message.is_error:
            events.append(Failed(message.result or f"The turn ended with {message.subtype}."))
        else:
            events.append(Finished(message.result or ""))
        return events
    return []


class SdkSession:
    """One turn on a connected SDK client."""

    def __init__(self, client: Any, prompt: str) -> None:
        self._client = client
        self._prompt = prompt

    async def events(self) -> AsyncIterator[TurnEvent]:
        await self._client.query(self._prompt)
        async for message in self._client.receive_response():
            for event in translate_message(message):
                yield event

    async def interrupt(self) -> None:
        await self._client.interrupt()


class SdkSessionFactory:
    def permission_callback(self, request: TurnRequest, can_use: CanUse):
        """The SDK's can_use_tool callback, answering through `can_use` (the Forge page)."""

        async def callback(tool_name: str, input_data: dict, _context: Any):
            if await can_use(tool_name, summarize_tool(tool_name, input_data)):
                return PermissionResultAllow(updated_input=input_data)
            return PermissionResultDeny(message=DECLINED, interrupt=False)

        return callback

    @asynccontextmanager
    async def open(self, request: TurnRequest, permission_mode: str, can_use: CanUse):
        options = ClaudeAgentOptions(
            cwd=request.folder,
            permission_mode=permission_mode,
            include_partial_messages=True,
            can_use_tool=self.permission_callback(request, can_use),
        )
        async with ClaudeSDKClient(options=options) as client:
            yield SdkSession(client, compose_prompt(request))
