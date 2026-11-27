"""Which URLs the service may fetch: public http(s) hosts only (SSRF guard).
The host is resolved here and every address must be public; redirects are covered by socket_guard.py."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from src.capabilities.media_downloader.utils.errors import DownloaderError, ErrorCode
from src.services.public_address import ALLOWED_PORTS, MAX_URL_LENGTH, is_public_ip

Resolver = Callable[[str], Awaitable[list[str]]]

async def system_resolver(host: str) -> list[str]:
    """Resolve through the event loop's executor, without blocking it."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class UrlPolicy:
    """Validates a user-supplied URL before any network fetch."""

    def __init__(self, resolver: Resolver | None = None) -> None:
        self._resolver = resolver or system_resolver

    async def check(self, url: str) -> str:
        """Return the trimmed URL, or raise DownloaderError (invalid_url / blocked_host)."""
        url = (url or "").strip()
        if not url or len(url) > MAX_URL_LENGTH:
            raise DownloaderError(ErrorCode.INVALID_URL, "That doesn't look like a valid link.")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise DownloaderError(ErrorCode.INVALID_URL, "That doesn't look like a valid link.") from None
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise DownloaderError(ErrorCode.INVALID_URL, "Paste a full link that starts with http:// or https://.")
        if parts.username or parts.password:
            raise DownloaderError(ErrorCode.INVALID_URL, "Links with a user name or password are not supported.")
        if port not in ALLOWED_PORTS:
            raise DownloaderError(ErrorCode.BLOCKED_HOST, "Only standard web ports (80 and 443) are allowed.")

        host = parts.hostname
        try:
            ipaddress.ip_address(host)
            addresses = [host]
        except ValueError:
            try:
                addresses = await self._resolver(host)
            except OSError:
                raise DownloaderError(ErrorCode.INVALID_URL, "That web address could not be found.") from None
        if not addresses or not all(is_public_ip(a) for a in addresses):
            raise DownloaderError(ErrorCode.BLOCKED_HOST, "That address is not a public website, so it can't be downloaded.")
        return url
