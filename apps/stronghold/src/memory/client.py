"""Account-scoped access to Armory's assistant memory, never a browser-selected owner."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
from src.service_auth import authenticate
from src.citadel_auth import requester_header
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

_MESSAGES = {
    404: "Memory is not enabled or this memory no longer exists",
    409: "This memory changed, duplicates another memory, or storage is full. Reload and try again.",
    422: "Memory must contain 1 to 500 characters",
}


class MemoryNote(BaseModel):
    id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)
    created_at: str


class MemoryError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


class MemoryClient:
    """`client` carries Armory's base URL; the caller closes it."""

    def __init__(self, client: httpx.AsyncClient, keyring=None) -> None:
        self._client = authenticate(client, "armory", keyring)


    async def request(self, method: str, uid: str, note_id: int | None = None,
                      body: dict | None = None) -> list[MemoryNote] | MemoryNote | None:
        path = f"/memory/owners/{quote(uid, safe='')}/notes"
        if note_id is not None:
            path += f"/{note_id}"
        try:
            response = await self._client.request(method, path, headers=requester_header(), json=body,
                                                  timeout=httpx.Timeout(10), follow_redirects=False)
        except httpx.HTTPError as error:
            raise MemoryError(503, "Memory storage is unavailable") from error
        if response.status_code in _MESSAGES:
            raise MemoryError(response.status_code, _MESSAGES[response.status_code])
        if not response.is_success:
            raise MemoryError(503, "Memory storage is unavailable")
        if method == "DELETE":
            return None
        try:
            data = response.json()
            return TypeAdapter(list[MemoryNote]).validate_python(data) if method == "GET" else MemoryNote.model_validate(data)
        except (ValueError, ValidationError) as error:
            raise MemoryError(503, "Memory storage returned an invalid response") from error

    async def purge(self, uid: str) -> bool:
        """Delete everything a deleted account kept. True only when Armory confirmed; never raises."""
        try:
            response = await self._client.delete(f"/memory/owners/{quote(uid, safe='')}", headers=requester_header(),
                                                 timeout=httpx.Timeout(5), follow_redirects=False)
        except httpx.HTTPError as error:
            logger.warning("memory purge request failed (%s)", type(error).__name__)
            return False
        if not response.is_success:
            logger.warning("memory purge was refused with status %s", response.status_code)
        return response.is_success
