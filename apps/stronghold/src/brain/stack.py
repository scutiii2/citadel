"""Short-term memory: a bounded stack of short items per chat.

One document per chat (collection brain_stacks, key "<uid>:<chat id>"). Every rule lives here so the
MCP tools, the REST routes and the turn engine cannot disagree.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from weakref import WeakValueDictionary

from src.brain.limits import StackLimits
from src.document_store import DocumentStore

STACKS = "brain_stacks"
_PAGE = 100
_PURGE_MAX_PAGES = 1000


class StackError(Exception):
    """A refused stack change; `status` is the HTTP code the REST routes answer."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _key(owner: str, chat_id: str) -> str:
    return f"{owner}:{chat_id}"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(text: str) -> str:
    return " ".join(str(text).split())


class StackStore:
    def __init__(self, store: DocumentStore, limits: StackLimits,
                 chat_generation: Callable[[str, str], Awaitable[str | None]] | None = None) -> None:
        self._store = store
        self._chat_generation = chat_generation
        self.limits = limits
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _lock(self, key: str) -> asyncio.Lock:
        # One process owns the store, so a per-stack lock makes read-change-write safe.
        return self._locks.setdefault(key, asyncio.Lock())

    async def _load(self, owner: str, chat_id: str) -> dict[str, Any]:
        generation = await self._chat_generation(owner, chat_id) if self._chat_generation else ""
        if generation is None:
            raise StackError(404, "No such chat.")
        doc = await self._store.get(STACKS, _key(owner, chat_id))
        if doc and doc.get("chat_generation") == generation:
            return doc
        return {"owner": owner, "chat_id": chat_id, "chat_generation": generation,
                "items": [], "next_id": 1, "updated_at": _now()}

    async def _save(self, doc: dict[str, Any]) -> None:
        doc["updated_at"] = _now()
        await self._store.put(STACKS, _key(doc["owner"], doc["chat_id"]), doc)

    def _view(self, doc: dict[str, Any]) -> dict[str, Any]:
        items = list(doc["items"])
        limit = self.limits.max_items
        return {"items": items, "used": len(items), "limit": limit,
                "warn": len(items) >= limit * self.limits.warn_ratio, "full": len(items) >= limit}

    async def view(self, owner: str, chat_id: str) -> dict[str, Any]:
        return self._view(await self._load(owner, chat_id))

    async def add(self, owner: str, chat_id: str, text: str, *, pinned: bool = False, source: str = "agent") -> dict[str, Any]:
        clean = _clean(text)
        if not clean:
            raise StackError(422, "The item cannot be empty.")
        if len(clean) > self.limits.max_item_chars:
            raise StackError(422, f"An item holds at most {self.limits.max_item_chars} characters.")
        async with self._lock(_key(owner, chat_id)):
            doc = await self._load(owner, chat_id)
            for item in doc["items"]:
                if item["text"].casefold() == clean.casefold():
                    return item
            items = doc["items"]
            while len(items) >= self.limits.max_items:
                oldest = next((i for i, item in enumerate(items) if not item["pinned"]), None)
                if oldest is None:
                    raise StackError(409, "The stack is full of pinned items. Unpin or remove one first.")
                del items[oldest]
            item = {"id": doc["next_id"], "text": clean, "pinned": bool(pinned), "source": source, "at": _now()}
            doc["next_id"] += 1
            items.append(item)
            await self._save(doc)
            return item

    def _find(self, doc: dict[str, Any], item_id: int) -> dict[str, Any]:
        for item in doc["items"]:
            if item["id"] == item_id:
                return item
        raise StackError(404, "No such item in this stack.")

    async def remove(self, owner: str, chat_id: str, item_id: int) -> None:
        async with self._lock(_key(owner, chat_id)):
            doc = await self._load(owner, chat_id)
            doc["items"].remove(self._find(doc, item_id))
            await self._save(doc)

    async def pin(self, owner: str, chat_id: str, item_id: int, pinned: bool) -> dict[str, Any]:
        async with self._lock(_key(owner, chat_id)):
            doc = await self._load(owner, chat_id)
            item = self._find(doc, item_id)
            item["pinned"] = bool(pinned)
            await self._save(doc)
            return item

    async def compaction_items(self, owner: str, chat_id: str) -> tuple[str, list[dict[str, Any]]]:
        doc = await self._load(owner, chat_id)
        return doc["chat_generation"], [item for item in doc["items"] if not item["pinned"]]

    async def apply_compaction(
        self, owner: str, chat_id: str, replaced_ids: list[int], text: str, *, expected_generation: str | None = None,
    ) -> dict[str, Any]:
        """Swap the named unpinned items for one compaction item placed first.

        With a generation, discard a summary if a sampled item changed during the model call."""
        clean = _clean(text)
        if not clean:
            raise StackError(422, "The summary cannot be empty.")
        if len(clean) > self.limits.compact_item_chars:
            raise StackError(422, f"A summary holds at most {self.limits.compact_item_chars} characters.")
        async with self._lock(_key(owner, chat_id)):
            doc = await self._load(owner, chat_id)
            requested = set(replaced_ids)
            doomed = {item["id"] for item in doc["items"] if item["id"] in requested and not item["pinned"]}
            if not doomed or (expected_generation is not None and (
                expected_generation != doc["chat_generation"] or doomed != requested
            )):
                raise StackError(409, "Nothing to replace; the stack changed.")
            kept = [item for item in doc["items"] if item["id"] not in doomed]
            summary = {"id": doc["next_id"], "text": clean, "pinned": False, "source": "compaction", "at": _now()}
            doc["next_id"] += 1
            doc["items"] = [summary, *kept]
            await self._save(doc)
            return summary

    async def delete(self, owner: str, chat_id: str, *, orphan_only: bool = False) -> None:
        async with self._lock(_key(owner, chat_id)):
            if orphan_only and self._chat_generation and await self._chat_generation(owner, chat_id) is not None:
                return
            await self._store.delete(STACKS, _key(owner, chat_id))

    async def purge_owner(self, owner: str) -> None:
        for _ in range(_PURGE_MAX_PAGES):
            docs = await self._store.query(STACKS, {"owner": owner}, limit=_PAGE)
            if not docs:
                return
            for doc in docs:
                await self.delete(owner, doc["chat_id"])
