"""Where a chat turn writes its error and chat-trace lines: Portcullis's logs (one store, shown in its admin pages)."""

from __future__ import annotations

from typing import Protocol

from src.platform import PortcullisClient


class TurnLogs(Protocol):
    async def error(self, uid: str, source: str, message: str, details: str | None = None) -> None: ...

    async def chat_trace(self, uid: str, message: str, details: str, prompts: str | None = None) -> None: ...


class PlatformLogs:
    def __init__(self, platform: PortcullisClient) -> None:
        self._platform = platform

    async def error(self, uid, source, message, details=None):
        await self._platform.write_log("error", uid, source, message, details)

    async def chat_trace(self, uid, message, details, prompts=None):
        await self._platform.write_log("chat_trace", uid, "chat.turn", message, details, prompts)
