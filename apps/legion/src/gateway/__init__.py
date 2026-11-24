"""The two model gateways, running inside Legion.

ChatService and DecisionService keep HTTP pools that belong to one event loop, and Legion calls them from several
loops and from worker threads. They therefore all run on one background loop here; callers hand work to it with
`call`, `call_sync` and `stream`.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, TypeVar

from src.runtime import config_files
from src.gateway.conversation.service import ChatService
from src.gateway.conversation.settings import Settings as ChatSettings
from src.gateway.conversation.store import GatewayStore as ChatStore
from src.gateway.decision.service import DecisionService
from src.gateway.decision.settings import Settings as DecisionSettings
from src.gateway.decision.store import GatewayStore as DecisionStore

T = TypeVar("T")
_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_chat: ChatService | None = None
_chat_store: ChatStore | None = None
_decision: DecisionService | None = None
_decision_store: DecisionStore | None = None


def _database() -> Path:
    """Legion's settings database; the entries are rows of its `conversation_gateways` and `decision_gateways` tables."""
    return config_files.SETTINGS_DB


def _service_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name="gateways", daemon=True).start()
            _loop = loop
        return _loop


def chat_service() -> ChatService:
    global _chat, _chat_store
    with _lock:
        if _chat is None:
            _chat_store = ChatStore(_database(), "conversation_gateways")
            _chat_store.seal_rows()
            _chat = ChatService(_chat_store, ChatSettings())
        return _chat


def decision_service() -> DecisionService:
    global _decision, _decision_store
    with _lock:
        if _decision is None:
            _decision_store = DecisionStore(_database(), "decision_gateways")
            _decision_store.seal_rows()
            _decision = DecisionService(_decision_store, DecisionSettings())
        return _decision


def chat_store() -> ChatStore:
    chat_service()
    assert _chat_store is not None
    return _chat_store


def decision_store() -> DecisionStore:
    decision_service()
    assert _decision_store is not None
    return _decision_store


async def call(awaitable: Awaitable[T]) -> T:
    """Run `awaitable` on the gateways' loop and wait for it from the caller's loop."""
    return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(_as_coroutine(awaitable), _service_loop()))


def call_sync(awaitable: Awaitable[T], timeout: float | None = None) -> T:
    """The same for a worker thread with no running loop."""
    return asyncio.run_coroutine_threadsafe(_as_coroutine(awaitable), _service_loop()).result(timeout)


async def stream(items: AsyncIterator[T]) -> AsyncIterator[T]:
    """Pull `items` (an async generator of a service) from the gateways' loop, one event at a time."""
    done = object()

    async def step() -> Any:
        try:
            return await items.__anext__()
        except StopAsyncIteration:
            return done

    try:
        while True:
            item = await call(step())
            if item is done:
                return
            yield item
    finally:
        aclose = getattr(items, "aclose", None)
        if aclose is not None:
            await call(aclose())


async def _as_coroutine(awaitable: Awaitable[T]) -> T:
    return await awaitable


async def close() -> None:
    """Release the HTTP pools at shutdown."""
    if _chat is not None:
        await call(_chat.aclose())
