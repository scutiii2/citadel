"""Calls to Armory that wait to be sent: which files each chat keeps, and which chats let theirs go.

One document per chat (and one per removed account), so a newer call replaces an older one."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

from src.document_store import DocumentStore
from src.schema.models import ChatFileHoldDoc, checked

HOLDS = "chat_file_holds"
HOLD, RELEASE, RELEASE_ALL = "hold", "release", "release_all"
_PAGE = 100


class ChatFileHolds:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store
        # A replacement must not land between `done` reading a document and deleting it.
        self._lock = asyncio.Lock()
        self.added = asyncio.Event()

    async def hold(self, owner: str, chat_id: str, file_ids: list[str]) -> None:
        await self._put(owner, chat_id, HOLD, file_ids)

    async def release(self, owner: str, chat_id: str) -> None:
        await self._put(owner, chat_id, RELEASE)

    async def release_account(self, owner: str) -> None:
        await self._put(owner, None, RELEASE_ALL)

    async def pending(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        while True:
            page = await self._store.query(HOLDS, limit=_PAGE, offset=len(docs))
            docs += page
            if len(page) < _PAGE:
                return docs

    async def done(self, doc: dict[str, Any]) -> None:
        """Removes a sent call, unless a newer one replaced it meanwhile."""
        async with self._lock:
            current = await self._store.get(HOLDS, doc["key"])
            if current is not None and current["version"] == doc["version"]:
                await self._store.delete(HOLDS, doc["key"])

    async def _put(self, owner: str, chat_id: str | None, op: str, file_ids: list[str] | None = None) -> None:
        key = f"{owner}:{chat_id or '*'}"
        doc = checked(ChatFileHoldDoc, {"key": key, "owner": owner, "chat_id": chat_id, "op": op,
                                        "file_ids": file_ids or [], "version": secrets.token_hex(8)})
        async with self._lock:
            await self._store.put(HOLDS, key, doc)
        self.added.set()
