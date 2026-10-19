"""L1 in-process cache: a TTL + LRU store and a write-through backend wrapper.

CachedBackend decorates any DatabaseBackend, so adapters and callers stay
unchanged. Reads hit the store first; writes go to the database, then drop the
affected entries. A ttl of 0 turns caching off for that connection.
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from src.backends.base import DatabaseBackend, Document

_MISS = object()


@dataclass(frozen=True)
class CacheSettings:
    ttl_seconds: float = 30.0
    max_entries: int = 1000
    negative_ttl_seconds: float = 5.0

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0 and self.max_entries > 0


class TtlLruCache:
    """Bounded map whose entries expire after their own ttl. Evicts least recently used."""

    def __init__(self, max_entries: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._max = max_entries
        self._clock = clock
        self._items: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()

    def get(self, key: Hashable) -> Any:
        entry = self._items.get(key)
        if entry is None:
            return _MISS
        expires, value = entry
        if self._clock() >= expires:
            del self._items[key]
            return _MISS
        self._items.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any, ttl: float) -> None:
        self._items[key] = (self._clock() + ttl, value)
        self._items.move_to_end(key)
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def discard(self, key: Hashable) -> None:
        self._items.pop(key, None)

    def discard_where(self, predicate: Callable[[Hashable], bool]) -> None:
        for key in [k for k in self._items if predicate(k)]:
            del self._items[key]

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


class CachedBackend(DatabaseBackend):
    def __init__(
        self, inner: DatabaseBackend, settings: CacheSettings, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._inner = inner
        self._settings = settings
        self._records = TtlLruCache(settings.max_entries, clock)
        self._queries = TtlLruCache(settings.max_entries, clock)
        self._inflight: dict[Hashable, asyncio.Future[Document | None]] = {}
        # Bumped on every write. A read stores its result only if no write to its
        # collection (or raw SQL) happened while it was in flight, else it could
        # overwrite fresher data with what it read before the write.
        self._epochs: dict[str, int] = {}
        self._sql_epoch = 0

    async def connect(self) -> None:
        await self._inner.connect()

    async def close(self) -> None:
        self._records.clear()
        self._queries.clear()
        await self._inner.close()

    async def get(self, collection: str, key: str) -> Document | None:
        if not self._settings.enabled:
            return await self._inner.get(collection, key)
        cache_key = (collection, key)
        cached = self._records.get(cache_key)
        if cached is not _MISS:
            return copy.deepcopy(cached)
        pending = self._inflight.get(cache_key)
        if pending is not None:  # another caller is already loading this key
            return copy.deepcopy(await asyncio.shield(pending))
        future: asyncio.Future[Document | None] = asyncio.get_running_loop().create_future()
        self._inflight[cache_key] = future
        stamp = self._stamp(collection)
        try:
            doc = await self._inner.get(collection, key)
        except BaseException as error:
            future.set_exception(error)
            future.exception()  # mark retrieved: no waiter may exist
            raise
        else:
            ttl = self._settings.ttl_seconds if doc is not None else self._settings.negative_ttl_seconds
            if ttl > 0 and stamp == self._stamp(collection):
                self._records.set(cache_key, copy.deepcopy(doc), ttl)
            future.set_result(doc)
            return copy.deepcopy(doc)
        finally:
            del self._inflight[cache_key]

    async def put(self, collection: str, key: str, doc: Document) -> None:
        await self._inner.put(collection, key, doc)
        self._invalidate(collection, key)

    async def create(self, collection: str, key: str, doc: Document) -> bool:
        created = await self._inner.create(collection, key, doc)
        # Also on False: a cached "not found" for this key is stale if another writer won.
        self._invalidate(collection, key)
        return created

    async def delete(self, collection: str, key: str) -> bool:
        removed = await self._inner.delete(collection, key)
        self._invalidate(collection, key)
        return removed

    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        if not self._settings.enabled:
            return await self._inner.query(collection, filters, limit, offset)
        cache_key = (collection, json.dumps(filters or {}, sort_keys=True), limit, offset)
        cached = self._queries.get(cache_key)
        if cached is not _MISS:
            return copy.deepcopy(cached)
        stamp = self._stamp(collection)
        docs = await self._inner.query(collection, filters, limit, offset)
        if stamp == self._stamp(collection):
            self._queries.set(cache_key, copy.deepcopy(docs), self._settings.ttl_seconds)
        return docs

    async def execute_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        rows = await self._inner.execute_sql(sql, params)
        self._sql_epoch += 1
        self._records.clear()  # raw SQL can change any collection
        self._queries.clear()
        return rows

    def _stamp(self, collection: str) -> tuple[int, int]:
        return self._sql_epoch, self._epochs.get(collection, 0)

    def _invalidate(self, collection: str, key: str) -> None:
        self._epochs[collection] = self._epochs.get(collection, 0) + 1
        self._records.discard((collection, key))
        self._queries.discard_where(lambda cache_key: cache_key[0] == collection)
