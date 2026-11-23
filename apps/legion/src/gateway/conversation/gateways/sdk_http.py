"""Bridge SDK httpx2 clients to the service's injectable httpx transport."""
from __future__ import annotations

from typing import AsyncIterator

import httpx
import httpx2


class ResponseStream(httpx2.AsyncByteStream):
    """Keep upstream streaming lazy and release the original response."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.response.aiter_raw():
            yield chunk

    async def aclose(self) -> None:
        await self.response.aclose()


class SDKTransport(httpx2.AsyncBaseTransport):
    """Convert request/response types without buffering response streams."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        mapped = httpx.Request(request.method, str(request.url), headers=request.headers.raw,
                               content=await request.aread(), extensions=request.extensions)
        try:
            response = await self.client.send(mapped, stream=True)
        except httpx.TimeoutException as error:
            raise httpx2.ReadTimeout("Upstream timeout", request=request) from error
        except httpx.HTTPError as error:
            raise httpx2.ConnectError("Upstream transport failure", request=request) from error
        if response.is_stream_consumed:
            return httpx2.Response(response.status_code, headers=response.headers.raw, content=response.content)
        return httpx2.Response(response.status_code, headers=response.headers.raw, stream=ResponseStream(response))


def sdk_client(client: httpx.AsyncClient, timeout: float) -> httpx2.AsyncClient:
    """All SDK traffic uses the same transport as Scuti and MockTransport tests."""
    return httpx2.AsyncClient(transport=SDKTransport(client), timeout=timeout, follow_redirects=False)