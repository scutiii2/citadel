"""Fixed, identity-scoped Armory gateways for native capability workspaces."""
from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx
from fastapi.responses import StreamingResponse

from src.models import Account
from src.services.mcp_server_info import base_url
from src.services.mcp_session import identity_headers

Area = Literal["pdf", "video"]
PUBLIC = {"pdf": "pdf-merger", "video": "video-downloader"}


class CapabilityFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


class CapabilityFilesGateway:
    def __init__(self, client: httpx.AsyncClient, mcp_url: str, token: str | None):
        self.client, self.base, self.token = client, base_url(mcp_url), token

    def headers(self, account: Account) -> dict[str, str]:
        return identity_headers(account.username, account.email, self.token, account.uid)

    async def request(self, area: Area, method: str, path: str, account: Account, **kwargs) -> Any:
        try:
            response = await self.client.request(
                method, f"{self.base}/{area}/ui{path}", headers=self.headers(account),
                timeout=120, follow_redirects=False, **kwargs,
            )
        except httpx.HTTPError as error:
            raise CapabilityFailure(502, "unavailable", "Armory is unreachable. Try again.") from error
        self.check(response)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as error:
            raise CapabilityFailure(502, "unavailable", "Armory returned an invalid response.") from error

    @staticmethod
    def check(response: httpx.Response) -> None:
        if 200 <= response.status_code < 300:
            return
        status = response.status_code
        code, message = "http_error", "The operation could not be completed."
        try:
            body = response.json()
            detail = body.get("error", body.get("detail", message))
            if isinstance(detail, dict):
                code, message = str(detail.get("code", code)), str(detail.get("message", message))
            elif isinstance(detail, str):
                message = detail
        except (ValueError, AttributeError):
            pass
        # URL policy and missing FFmpeg are user-actionable service refusals;
        # an upstream authentication failure must not look like browser auth.
        if (status == 403 and code == "blocked_host") or (status == 503 and code == "ffmpeg_missing"):
            raise CapabilityFailure(status, code, message)
        if status in (401, 403) or status >= 500 or 300 <= status < 400:
            raise CapabilityFailure(502, "unavailable", "Armory is unavailable; check its internal connection.")
        raise CapabilityFailure(status if status in (400, 404, 409, 413, 416, 422, 429) else 400, code, message)

    def local_links(self, area: Area, value: Any) -> Any:
        """Never expose an internal origin or bearer signature to the browser."""
        if isinstance(value, list):
            return [self.local_links(area, item) for item in value]
        if isinstance(value, dict):
            result = {key: self.local_links(area, item) for key, item in value.items()}
            if "download_url" in result:
                file_id = quote(str(result.get("file_id", "")), safe="")
                result["download_url"] = f"/api/{PUBLIC[area]}/files/{file_id}/download"
            return result
        return value

    async def stream(self, area: Area, file_id: str, account: Account, *, content=False, range_header=None):
        encoded = quote(file_id, safe="")
        if content:
            url = f"{self.base}/{area}/ui/files/{encoded}/content"
        else:
            # Ownership is checked before minting/fetching a signed bearer link.
            files = await self.request(area, "GET", "/files", account)
            if not isinstance(files, list) or any(not isinstance(file, dict) for file in files):
                raise CapabilityFailure(502, "unavailable", "Armory returned an invalid file list.")
            file = next((f for f in files if f.get("file_id") == file_id), None)
            if file is None:
                raise CapabilityFailure(404, "file_not_found", "File expired or unavailable; upload again if expired.")
            try:
                signed = urlsplit(str(file.get("download_url", "")))
            except ValueError as error:
                raise CapabilityFailure(502, "unavailable", "Armory returned an invalid download link.") from error
            if not signed.path.endswith(f"/{area}/files/{encoded}/download") or not signed.query:
                raise CapabilityFailure(502, "unavailable", "Armory returned an invalid download link.")
            # Use only the fixed upstream origin, never an URL supplied by a browser or file.
            url = f"{self.base}/{area}/files/{encoded}/download?{signed.query}"
        headers = self.headers(account)
        headers["Accept-Encoding"] = "identity"
        if range_header:
            headers["Range"] = range_header
        request = self.client.build_request("GET", url, headers=headers, timeout=120)
        try:
            response = await self.client.send(request, stream=True, follow_redirects=False)
        except httpx.HTTPError as error:
            raise CapabilityFailure(502, "unavailable", "Armory is unreachable.") from error
        if response.status_code not in (200, 206):
            try:
                await response.aread()
                self.check(response)
                raise CapabilityFailure(502, "unavailable", "Armory returned an invalid file response.")
            finally:
                await response.aclose()
        async def chunks():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
        forwarded = {k: v for k, v in response.headers.items() if k.lower() in (
            "content-type", "content-length", "content-disposition", "content-range", "accept-ranges",
        )}
        forwarded.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})
        if response.headers.get("content-encoding"):
            forwarded.pop("content-length", None)  # aiter_bytes decodes upstream compression
        if content:
            forwarded["Content-Security-Policy"] = "sandbox"
        return StreamingResponse(chunks(), status_code=response.status_code, headers=forwarded)
