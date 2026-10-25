"""Uploads an attached audio file to Scribe, which owns it for 24 hours.

Scribe checks the owner from the identity headers; the browser never learns
Scribe's origin or the internal token."""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from src.models import Account
from src.services.mcp_session import identity_headers


class ScribeGateway:
    def __init__(self, client: httpx.AsyncClient, base_url: str, token: str | None):
        self.client, self.base, self.token = client, base_url.rstrip("/"), token

    async def upload(self, account: Account, filename: str, content: bytes) -> dict:
        return await self._audio_request("files", account, filename, content)

    async def transcribe(self, account: Account, filename: str, content: bytes) -> dict:
        """Transcribe through the same owner, quota and cache as attached audio."""
        return await self._audio_request("transcribe", account, filename, content)

    async def _audio_request(self, endpoint: str, account: Account, filename: str, content: bytes) -> dict:
        headers = identity_headers(account.username, account.email, self.token, account.uid)
        headers["X-Filename"] = filename
        headers["Content-Type"] = "application/octet-stream"
        try:
            response = await self.client.post(f"{self.base}/api/{endpoint}", headers=headers, content=content, timeout=120)
        except httpx.HTTPError as error:
            raise HTTPException(502, "Scribe is unreachable. Try again.") from error
        if response.status_code == 200:
            return response.json()
        if response.status_code in (400, 413):
            try:
                message = response.json().get("message")
            except ValueError:
                message = None
            raise HTTPException(response.status_code, message or "Scribe rejected the audio.")
        raise HTTPException(502, "Scribe is unavailable; check its internal connection.")
