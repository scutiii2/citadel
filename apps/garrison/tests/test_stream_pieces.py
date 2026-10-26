"""anthropic_provider._stream_pieces: thinking and tool-call JSON are yielded
(for the live token meter) but flagged as not-text, so they never reach the
user as answer text."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, Mock

from anthropic.lib.streaming import AsyncMessageStream, InputJsonEvent, TextEvent
from anthropic.lib.streaming._types import ThinkingEvent

from src.providers.language.anthropic_provider import _stream_pieces


def _collect(stream):
    async def run():
        return [piece async for piece in _stream_pieces(stream)]
    return asyncio.run(run())


def _sdk_stream(events):
    async def aiter():
        for event in events:
            yield event
    stream = MagicMock(spec=AsyncMessageStream)
    stream.__aiter__ = Mock(return_value=aiter())
    return stream


def test_real_stream_yields_text_thinking_and_tool_json_with_the_right_flag():
    stream = _sdk_stream([
        ThinkingEvent(type="thinking", thinking="hmm", snapshot="hmm"),
        TextEvent(type="text", text="Hello", snapshot="Hello"),
        InputJsonEvent(type="input_json", partial_json='{"a":', snapshot={}),
        MagicMock(type="content_block_stop"),
    ])

    assert _collect(stream) == [(False, "hmm"), (True, "Hello"), (False, '{"a":')]


def test_a_stream_without_sdk_events_falls_back_to_its_text():
    async def gen():
        yield "one"
        yield "two"
    stream = MagicMock()
    stream.text_stream = gen()

    assert _collect(stream) == [(True, "one"), (True, "two")]
