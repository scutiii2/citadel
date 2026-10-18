from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import AssistantMessage, PermissionResultAllow, PermissionResultDeny, ResultMessage  # noqa: E402
from claude_agent_sdk.types import TextBlock, ToolUseBlock  # noqa: E402

from src.events import Failed, Finished, TextDelta, ToolCall, TurnRequest, UsageReport  # noqa: E402
from src.providers.claude_sdk import SdkSession, SdkSessionFactory, translate_message  # noqa: E402

try:
    from claude_agent_sdk import StreamEvent
except ImportError:  # older layout
    from claude_agent_sdk.types import StreamEvent


def result(**overrides) -> ResultMessage:
    fields = dict(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="s",
        result="All done", usage={"input_tokens": 11, "output_tokens": 22},
    )
    return ResultMessage(**{**fields, **overrides})


def test_text_deltas_come_from_stream_events() -> None:
    event = StreamEvent(
        uuid="u", session_id="s",
        event={"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
    )

    assert translate_message(event) == [TextDelta("Hel")]


def test_other_stream_events_are_ignored() -> None:
    for inner in (
        {"type": "message_start"},
        {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}},
        {"type": "content_block_delta"},
    ):
        assert translate_message(StreamEvent(uuid="u", session_id="s", event=inner)) == []


def test_tool_use_blocks_become_tool_calls_and_text_blocks_are_not_repeated() -> None:
    message = AssistantMessage(
        content=[TextBlock(text="Running tests"), ToolUseBlock(id="1", name="Bash", input={"command": "npm test"})],
        model="m",
    )

    assert translate_message(message) == [ToolCall("Bash", "npm test")]


def test_a_subagents_messages_are_skipped() -> None:
    message = AssistantMessage(
        content=[ToolUseBlock(id="1", name="Bash", input={"command": "ls"})], model="m", parent_tool_use_id="parent"
    )

    assert translate_message(message) == []


def test_a_successful_result_reports_usage_then_the_answer() -> None:
    assert translate_message(result()) == [UsageReport(11, 22), Finished("All done")]


def test_a_result_without_usage_or_text() -> None:
    assert translate_message(result(usage=None, result=None)) == [Finished("")]


def test_an_error_result_fails_the_turn() -> None:
    assert translate_message(result(is_error=True, subtype="error_during_execution", result=None, usage=None)) == [
        Failed("The turn ended with error_during_execution.")
    ]
    assert translate_message(result(is_error=True, result="Credit balance too low", usage=None)) == [
        Failed("Credit balance too low")
    ]


def test_unknown_messages_are_ignored() -> None:
    assert translate_message(object()) == []
    assert translate_message("text") == []


class FakeClient:
    def __init__(self, messages) -> None:
        self.messages, self.queries, self.interrupted = messages, [], False

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        for message in self.messages:
            yield message

    async def interrupt(self) -> None:
        self.interrupted = True


def test_a_session_sends_the_prompt_and_translates_the_reply() -> None:
    client = FakeClient([result()])
    session = SdkSession(client, "hello")

    async def go():
        events = [event async for event in session.events()]
        await session.interrupt()
        return events

    assert asyncio.run(go()) == [UsageReport(11, 22), Finished("All done")]
    assert client.queries == ["hello"] and client.interrupted is True


def test_the_permission_callback_adapter_allows_and_denies() -> None:
    request = TurnRequest("t", 1, ".", "ask", "go")
    seen = []

    async def allow_bash(tool: str, summary: str) -> bool:
        seen.append((tool, summary))
        return tool == "Bash"

    callback = SdkSessionFactory().permission_callback(request, allow_bash)

    allowed = asyncio.run(callback("Bash", {"command": "ls"}, object()))
    denied = asyncio.run(callback("Write", {"file_path": "a.py"}, object()))

    assert isinstance(allowed, PermissionResultAllow) and allowed.updated_input == {"command": "ls"}
    assert isinstance(denied, PermissionResultDeny) and denied.message and denied.interrupt is False
    assert seen == [("Bash", "ls"), ("Write", "a.py")]
