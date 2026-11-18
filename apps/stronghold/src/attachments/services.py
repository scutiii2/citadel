"""Stronghold's clients for the tool services that take a user's files: Scribe (audio), Reader
(documents), Bard (speech) and Armory's upload routes (PDFs, tables).

Each call carries the requester's identity and the service's own token. The services answer 4xx
with their own safe message; that message is kept, anything else becomes a 502 the browser can read.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from src.requester import Requester
from src.service_auth import authenticate
from src.citadel_auth import requester_header

_LONG = 120.0
_STREAMED = ("content-type", "content-length", "content-range", "accept-ranges")


def _headers(who: Requester, token: str | None) -> dict[str, str]:
    headers = {"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid}
    if token:
        headers["X-Internal-Token"] = token
    return headers


def _message(response: httpx.Response, key: str) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    value = body.get(key) if isinstance(body, dict) else None
    return value if isinstance(value, str) and value else None


class ToolService:
    """One tool service. `client` carries its base URL; `rejected` maps the 4xx codes it uses to refuse
    a file to the status Stronghold answers; every other answer is a 502."""

    def __init__(self, client: httpx.AsyncClient, token: str | None, name: str, rejected: dict[int, int],
                 refusal: str) -> None:
        self._client, self._token, self._name = client, token, name
        self._rejected, self._refusal = rejected, refusal

    def set_token(self, token: str | None) -> None:
        """Use a new token from the next request on."""
        self._token = token or None

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    async def _send(self, method: str, path: str, who: Requester, **kwargs: Any) -> dict:
        try:
            response = await self._client.request(method, path, headers={**_headers(who, self._token), **kwargs.pop("headers", {})},
                                                  timeout=_LONG, follow_redirects=False, **kwargs)
        except httpx.HTTPError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{self._name} is unreachable. Try again.") from error
        if response.status_code == 200:
            return response.json()
        if response.status_code in self._rejected:
            raise HTTPException(self._rejected[response.status_code], _message(response, "message") or self._refusal)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{self._name} is unavailable; check its internal connection.")

    async def post_file(self, path: str, who: Requester, filename: str, content: bytes) -> dict:
        return await self._send("POST", path, who, content=content,
                                headers={"X-Filename": filename, "Content-Type": "application/octet-stream"})

    async def call(self, method: str, path: str, who: Requester, body: dict | None = None) -> dict:
        return await self._send(method, path, who, json=body)

    async def stream(self, path: str, who: Requester, range_header: str | None = None) -> StreamingResponse:
        """GET a stored file as a stream, with the browser's Range header, so a player can seek.
        404 and 416 keep their meaning (the file expired); every other refusal is a 502."""
        headers = {**_headers(who, self._token), "Accept-Encoding": "identity"}
        if range_header:
            headers["Range"] = range_header
        request = self._client.build_request("GET", path, headers=headers, timeout=_LONG)
        try:
            response = await self._client.send(request, stream=True, follow_redirects=False)
        except httpx.HTTPError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{self._name} is unreachable. Try again.") from error
        if response.status_code not in (200, 206):
            await response.aread()
            await response.aclose()
            if response.status_code in (404, 416):
                raise HTTPException(response.status_code, "The file expired or is unavailable.")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{self._name} is unavailable; check its internal connection.")

        async def chunks():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()

        kept = {k: v for k, v in response.headers.items() if k.lower() in _STREAMED}
        return StreamingResponse(chunks(), status_code=response.status_code, headers=kept)


def scribe(client: httpx.AsyncClient, token: str | None) -> ToolService:
    return ToolService(client, token, "Scribe", {400: 400, 413: 413}, "Scribe rejected the audio.")


def reader(client: httpx.AsyncClient, token: str | None) -> ToolService:
    return ToolService(client, token, "Reader", {400: 400, 413: 413, 422: 400}, "Reader rejected the document.")


def bard(client: httpx.AsyncClient, token: str | None) -> ToolService:
    return ToolService(client, token, "Bard", {400: 400, 413: 413}, "Bard rejected the text or voice.")


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
