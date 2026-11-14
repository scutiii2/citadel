"""Uploads an attached document to Reader, which owns it for 24 hours.

Reader checks the owner from the identity headers; the browser never learns
Reader's origin or its token."""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from src.models import Account
from src.services.mcp_session import identity_headers


class ReaderGateway:
    def __init__(self, client: httpx.AsyncClient, base_url: str, token: str | None):
        self.client, self.base, self.token = client, base_url.rstrip("/"), token

    async def upload(self, account: Account, filename: str, content: bytes) -> dict:
        headers = identity_headers(account.username, account.email, self.token, account.uid)
        headers["X-Filename"] = filename
        headers["Content-Type"] = "application/octet-stream"
        try:
            response = await self.client.post(f"{self.base}/api/files", headers=headers, content=content, timeout=120)
        except httpx.HTTPError as error:
            raise HTTPException(502, "Reader is unreachable. Try again.") from error
        if response.status_code == 200:
            return response.json()
        if response.status_code in (400, 413, 422):
            try:
                message = response.json().get("message")
            except ValueError:
                message = None
            raise HTTPException(413 if response.status_code == 413 else 400, message or "Reader rejected the document.")
        raise HTTPException(502, "Reader is unavailable; check its internal connection.")
