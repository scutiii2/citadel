"""Client for db_gateway: key/document storage that lives outside ember_api's own database.

Used for new data that needs no joins or foreign keys. Accounts, chats and the rest stay
in SQLAlchemy. A call fails with DbGatewayUnavailable when the gateway cannot be reached,
so a feature that uses it fails alone and ember_api itself keeps running.
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import quote

import httpx

Document = dict[str, Any]

# db_gateway answers a missing record with 404 and an error starting like this;
# 404 for an unknown instance or connection has a different message.
_NO_RECORD = "no record"


class DbGatewayError(Exception):
    pass


class DbGatewayUnavailable(DbGatewayError):
    pass


class DocumentStore(Protocol):
    async def get(self, collection: str, key: str) -> Document | None: ...

    async def put(self, collection: str, key: str, doc: Document) -> None: ...

    async def delete(self, collection: str, key: str) -> bool: ...

    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]: ...


class DbGatewayClient:
    """One instance and connection of db_gateway, reached over HTTP with the internal token.

    `client` carries the gateway's base URL and a timeout; the caller closes it."""

    def __init__(self, client: httpx.AsyncClient, instance: str, connection: str, internal_token: str | None) -> None:
        self._client = client
        self._base = f"/instances/{quote(instance, safe='')}/connections/{quote(connection, safe='')}"
        self._headers = {"X-Internal-Token": internal_token} if internal_token else {}

    def _record(self, collection: str, key: str) -> str:
        return f"{self._base}/collections/{quote(collection, safe='')}/records/{quote(key, safe='')}"

    async def _send(self, method: str, path: str, json: Any = None) -> httpx.Response:
        try:
            return await self._client.request(method, path, json=json, headers=self._headers)
        except httpx.TransportError as error:
            raise DbGatewayUnavailable(f"db_gateway is not reachable: {error.__class__.__name__}") from error

    @staticmethod
    def _is_missing_record(response: httpx.Response) -> bool:
        return response.status_code == 404 and _error_text(response).startswith(_NO_RECORD)

    @staticmethod
    def _check(response: httpx.Response) -> httpx.Response:
        if response.status_code >= 400:
            raise DbGatewayError(f"db_gateway answered {response.status_code}: {_error_text(response)}")
        return response

    async def get(self, collection: str, key: str) -> Document | None:
        response = await self._send("GET", self._record(collection, key))
        if self._is_missing_record(response):
            return None
        return self._check(response).json()["doc"]

    async def put(self, collection: str, key: str, doc: Document) -> None:
        self._check(await self._send("PUT", self._record(collection, key), {"doc": doc}))

    async def delete(self, collection: str, key: str) -> bool:
        response = await self._send("DELETE", self._record(collection, key))
        if self._is_missing_record(response):
            return False
        self._check(response)
        return True

    async def query(
        self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        path = f"{self._base}/collections/{quote(collection, safe='')}/query"
        body = {"filters": filters or {}, "limit": limit, "offset": offset}
        return self._check(await self._send("POST", path, body)).json()["docs"]


def _error_text(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", ""))
    except (ValueError, AttributeError):
        return response.text[:200]
