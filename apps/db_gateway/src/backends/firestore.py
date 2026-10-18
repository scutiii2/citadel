"""Firestore adapter (google-cloud-firestore AsyncClient).

Native mapping: collection -> Firestore collection, key -> document id, doc -> document fields.
The library is imported on connect, so it is only needed for Firestore connections.
Set FIRESTORE_EMULATOR_HOST to run against the local emulator instead of the cloud.
"""

from __future__ import annotations

import inspect
from typing import Any

from src.backends.base import DatabaseBackend, Document


def _check_key(key: str) -> str:
    if not key or "/" in key or key in (".", ".."):
        raise ValueError(f"Firestore document id must be non-empty and contain no '/', got {key!r}")
    return key


class FirestoreBackend(DatabaseBackend):
    def __init__(self, project: str | None = None, credentials_file: str | None = None, database: str | None = None) -> None:
        self._project = project
        self._credentials_file = credentials_file
        self._database = database
        self._client: Any = None

    async def connect(self) -> None:
        try:
            from google.cloud import firestore
        except ImportError as error:
            raise RuntimeError("Firestore connections need google-cloud-firestore: pip install -e \".[firestore]\"") from error
        options = {k: v for k, v in (("project", self._project), ("database", self._database)) if v}
        if self._credentials_file:
            self._client = firestore.AsyncClient.from_service_account_json(self._credentials_file, **options)
        else:
            self._client = firestore.AsyncClient(**options)

    async def close(self) -> None:
        if self._client is not None:
            result = self._client.close()
            if inspect.isawaitable(result):
                await result
            self._client = None

    def _db(self) -> Any:
        if self._client is None:
            raise RuntimeError("backend is not connected")
        return self._client

    async def get(self, collection: str, key: str) -> Document | None:
        snapshot = await self._db().collection(collection).document(_check_key(key)).get()
        return snapshot.to_dict() if snapshot.exists else None

    async def put(self, collection: str, key: str, doc: Document) -> None:
        await self._db().collection(collection).document(_check_key(key)).set(doc)

    async def create(self, collection: str, key: str, doc: Document) -> bool:
        from google.api_core.exceptions import AlreadyExists

        try:  # create() fails atomically when the document exists
            await self._db().collection(collection).document(_check_key(key)).create(doc)
        except AlreadyExists:
            return False
        return True

    async def delete(self, collection: str, key: str) -> bool:
        from google.api_core.exceptions import NotFound

        client = self._db()
        reference = client.collection(collection).document(_check_key(key))
        try:  # exists=True makes the delete fail atomically when the document is absent
            await reference.delete(option=client.write_option(exists=True))
        except NotFound:
            return False
        return True

    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query: Any = self._db().collection(collection)
        for field, value in (filters or {}).items():
            query = query.where(filter=FieldFilter(field, "==", value))
        query = query.order_by("__name__").limit(limit).offset(offset)
        return [snapshot.to_dict() async for snapshot in query.stream()]
