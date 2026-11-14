"""_stream_pieces: a round's stream as (is_text, chunk) pairs. The gateway shim
streams answer text only, so every chunk is text."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.providers.language.anthropic_provider import _stream_pieces


def _collect(stream):
    async def run():
        return [piece async for piece in _stream_pieces(stream)]
    return asyncio.run(run())


def test_a_stream_yields_its_text():
    async def gen():
        yield "one"
        yield "two"
    stream = MagicMock()
    stream.text_stream = gen()

    assert _collect(stream) == [(True, "one"), (True, "two")]
