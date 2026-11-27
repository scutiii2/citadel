"""Where allowances are kept: one document per account in "usage_allowances".

Every change is a read, change and write under one lock per account, so one reset cannot be spent twice. That
relies on Stronghold running as one process, as the turn engine does.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from src.document_store import DocumentStore
from src.schema.models import UsageAllowanceDoc, checked
from src.usage.allowance import Allowance

COLLECTION = "usage_allowances"
_PAGE = 500


class AllowanceStore:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, owner: str) -> asyncio.Lock:
        return self._locks.setdefault(owner, asyncio.Lock())

    async def read(self, owner: str) -> Allowance:
        return Allowance.from_doc(owner, await self._store.get(COLLECTION, owner))

    async def all(self) -> list[Allowance]:
        docs: list[dict] = []
        while True:
            page = await self._store.query(COLLECTION, {}, limit=_PAGE, offset=len(docs))
            docs += page
            if len(page) < _PAGE:
                return [Allowance.from_doc(doc["owner"], doc) for doc in docs]

    @asynccontextmanager
    async def change(self, owner: str, now: datetime) -> AsyncIterator[Allowance]:
        """The account's allowance, saved when the block ends. An error inside it saves nothing."""
        async with self._lock(owner):
            allowance = await self.read(owner)
            yield allowance
            allowance.prune(now)
            await self._store.put(COLLECTION, owner, checked(UsageAllowanceDoc, allowance.to_doc()))

    async def delete(self, owner: str) -> None:
        async with self._lock(owner):
            await self._store.delete(COLLECTION, owner)
