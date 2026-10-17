"""Account-scoped access to mcp_server's existing memory, never a browser-selected owner."""
from __future__ import annotations

from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from src.services.mcp_server_info import base_url


class MemoryNote(BaseModel):
    id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)
    created_at: str


class MemoryError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


class MemoryClient:
    def __init__(self, client: httpx.AsyncClient, mcp_url: str, token: str | None) -> None:
        self._client = client
        self._base = base_url(mcp_url)
        self._headers = {"X-Internal-Token": token} if token else {}

    async def request(self, method: str, uid: str, note_id: int | None = None,
                      body: dict | None = None) -> list[MemoryNote] | MemoryNote | None:
        path = f"{self._base}/memory/owners/{quote(uid, safe='')}/notes"
        if note_id is not None:
            path += f"/{note_id}"
        try:
            response = await self._client.request(method, path, headers=self._headers, json=body,
                                                  timeout=httpx.Timeout(10), follow_redirects=False)
        except httpx.HTTPError as error:
            raise MemoryError(503, "Memory storage is unavailable") from error
        if response.status_code in (404, 409, 422):
            messages = {404: "Memory is not enabled or this memory no longer exists",
                        409: "This memory changed, duplicates another memory, or storage is full. Reload and try again.",
                        422: "Memory must contain 1 to 500 characters"}
            raise MemoryError(response.status_code, messages[response.status_code])
        if not response.is_success:
            raise MemoryError(503, "Memory storage is unavailable")
        if method == "DELETE":
            return None
        try:
            data = response.json()
            return TypeAdapter(list[MemoryNote]).validate_python(data) if method == "GET" else MemoryNote.model_validate(data)
        except (ValueError, ValidationError) as error:
            raise MemoryError(503, "Memory storage returned an invalid response") from error
