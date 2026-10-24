"""Fetching an ICS feed safely: https only, public addresses only, capped in size.

shortcut: the address is checked, then httpx connects by name, so a DNS answer that changes between
the two calls (rebinding) is not blocked. Pin the checked address in the transport if that matters.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

MAX_URL = 2000
MAX_REDIRECTS = 3

Resolver = Callable[[str, int], Awaitable[list[str]]]


class FeedError(Exception):
    """A feed that cannot be used. The message is safe to show and never holds the URL."""


def clean_feed_url(raw: str) -> str:
    """`webcal:` becomes `https:`; anything but https is refused."""
    url = raw.strip()
    if url.lower().startswith("webcal:"):
        url = "https:" + url[len("webcal:"):]
    parts = urlsplit(url)
    if not url or len(url) > MAX_URL or parts.scheme.lower() != "https" or not parts.hostname:
        raise FeedError("Enter an https:// or webcal:// link")
    if parts.username is not None or parts.password is not None:
        raise FeedError("The link must not contain a user name or password")
    return url


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


@dataclass(frozen=True)
class FetchResult:
    body: bytes | None  # None when the server said "not modified"
    etag: str | None

    @property
    def not_modified(self) -> bool:
        return self.body is None


class CalendarFetcher:
    """`client` must not follow redirects: this class follows them itself so that every hop is checked."""

    def __init__(
        self, client: httpx.AsyncClient, *, max_bytes: int, allow_private_urls: bool = False,
        resolve: Resolver = system_resolver,
    ) -> None:
        self._client = client
        self._max_bytes = max_bytes
        self._allow_private = allow_private_urls
        self._resolve = resolve

    async def _check_host(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme.lower() != "https":
            raise FeedError("The feed redirected to a link that is not https")
        if self._allow_private:
            return
        try:
            addresses = await self._resolve(parts.hostname or "", parts.port or 443)
        except OSError:
            raise FeedError("The feed's address could not be found") from None
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global or ip.is_multicast:
                raise FeedError("That address is not allowed")

    async def fetch(self, url: str, etag: str | None = None) -> FetchResult:
        headers = {"Accept": "text/calendar, */*;q=0.5"}
        if etag:
            headers["If-None-Match"] = etag
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await self._check_host(current)
            try:
                async with self._client.stream("GET", current, headers=headers) as response:
                    if response.status_code == 304:
                        return FetchResult(None, etag)
                    if response.is_redirect:
                        target = response.headers.get("location", "")
                        if not target:
                            raise FeedError("The feed redirected without a target")
                        current = urljoin(current, target)
                        continue
                    if response.status_code != 200:
                        raise FeedError(f"The feed answered HTTP {response.status_code}")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise FeedError("The feed is too large")
                    return FetchResult(bytes(body), response.headers.get("etag"))
            except httpx.HTTPError:
                raise FeedError("The feed could not be reached") from None
        raise FeedError("The feed redirected too many times")
