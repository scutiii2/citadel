"""The one interface every database adapter implements.

The common surface is a document store: a record is a JSON object addressed by
(collection, key). It maps onto a SQLite/SQL table and onto Firestore alike.
Backend-specific features (raw SQL) are optional and raise UnsupportedOperation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

Document = dict[str, Any]


class UnsupportedOperation(Exception):
    """The backend does not offer this operation."""


class DatabaseBackend(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def get(self, collection: str, key: str) -> Document | None: ...

    @abstractmethod
    async def put(self, collection: str, key: str, doc: Document) -> None: ...

    @abstractmethod
    async def delete(self, collection: str, key: str) -> bool:
        """True when a record existed and was removed."""

    @abstractmethod
    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        """Records whose top-level fields equal every filter value, ordered by key."""

    async def execute_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        raise UnsupportedOperation(f"{type(self).__name__} does not support raw SQL")
