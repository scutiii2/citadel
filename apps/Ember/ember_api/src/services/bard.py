"""Streams a stored Bard audio file to the signed-in browser.

Bard owns the files and checks the owner from the identity headers; the browser
never learns Bard's origin or the internal token."""
from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.models import Account
from src.services.mcp_session import identity_headers

_FORWARDED = ("content-type", "content-length", "content-range", "accept-ranges")


class BardGateway:
    def __init__(self, client: httpx.AsyncClient, base_url: str, token: str | None):
        self.client, self.base, self.token = client, base_url.rstrip("/"), token

    async def stream(self, file_id: str, account: Account, range_header: str | None = None) -> StreamingResponse:
        headers = identity_headers(account.username, account.email, self.token, account.uid)
        headers["Accept-Encoding"] = "identity"
        if range_header:
            headers["Range"] = range_header
        request = self.client.build_request(
            "GET", f"{self.base}/api/files/{quote(file_id, safe='')}", headers=headers, timeout=60
        )
        try:
            response = await self.client.send(request, stream=True, follow_redirects=False)
        except httpx.HTTPError as error:
            raise HTTPException(502, "Bard is unreachable. Try again.") from error
        if response.status_code not in (200, 206):
            await response.aread()
            await response.aclose()
            if response.status_code in (404, 416):
                raise HTTPException(response.status_code, "The audio expired or is unavailable.")
            raise HTTPException(502, "Bard is unavailable; check its internal connection.")

        async def chunks():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()

        forwarded = {k: v for k, v in response.headers.items() if k.lower() in _FORWARDED}
        forwarded.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Disposition": 'inline; filename="bard.mp3"',
        })
        if response.headers.get("content-encoding"):
            forwarded.pop("content-length", None)
        return StreamingResponse(chunks(), status_code=response.status_code, headers=forwarded)
