"""Signed Armory clients for PDF and table uploads."""

from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from src.citadel_auth import requester_header
from src.requester import Requester
from src.service_auth import authenticate

_LONG = 120.0


class ArmoryUploads:
    """Armory's /upload/pdf and /upload/table: it keeps the file for the data and PDF tools and answers with an id."""

    def __init__(self, client: httpx.AsyncClient, keyring=None) -> None:
        self._client = authenticate(client, "armory", keyring)

    async def _upload(self, path: str, who: Requester, filename: str, content: bytes, down: str) -> dict:
        try:
            response = await self._client.post(path, files={"file": (filename, content)}, headers=requester_header(),
                                               timeout=_LONG, follow_redirects=False)
        except httpx.HTTPError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, down) from error
        try:
            body = response.json()
        except ValueError:
            body = None
        if 400 <= response.status_code < 500:
            if response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
                # Our own token was refused: a setup fault, not something the user did.
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, down)
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                str((body.get("error") if isinstance(body, dict) else None) or f"armory answered {response.status_code}"))
        if response.status_code >= 500 or not isinstance(body, dict):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, down)
        return body

    async def pdf(self, who: Requester, filename: str, content: bytes) -> dict:
        body = await self._upload("/upload/pdf", who, filename, content,
                                  "PDF upload is unavailable; check the pdf_merger extension")
        if (not isinstance(body.get("file_id"), str) or not isinstance(body.get("pages"), int)
                or not isinstance(body.get("kind"), str) or not isinstance(body.get("expires_at"), (int, float))):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "PDF upload is unavailable; check the pdf_merger extension")
        return body

    async def table(self, who: Requester, filename: str, content: bytes) -> dict:
        body = await self._upload("/upload/table", who, filename, content, "armory is unreachable")
        if not isinstance(body.get("table_id"), str):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "armory is unreachable")
        return body
