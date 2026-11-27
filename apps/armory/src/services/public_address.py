"""Which web addresses Armory may open or hand to an outside fetcher: public http(s) hosts only (SSRF guard)."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Collection
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048
ALLOWED_PORTS = (None, 80, 443)

_NAT64 = ipaddress.IPv6Network("64:ff9b::/96")
_IPV4_COMPATIBLE = ipaddress.IPv6Network("::/96")


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address hidden in an IPv4-mapped, NAT64 or IPv4-compatible IPv6 address."""
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address in _NAT64 or (address in _IPV4_COMPATIBLE and int(address) > 1):  # not :: or ::1
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def is_public_ip(ip: str) -> bool:
    """True only for globally routable unicast addresses; IPv4 embedded in IPv6 is unwrapped first."""
    try:
        address = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(address)
        if embedded is not None:
            address = embedded
    return address.is_global and not address.is_multicast


def require_public_url(
    url: str,
    *,
    allows_ip: Callable[[str], bool] = is_public_ip,
    ports: Collection[int | None] | None = ALLOWED_PORTS,
    resolver: Callable = socket.getaddrinfo,
) -> str:
    """The trimmed URL when every address of its host is public; else ValueError with a message safe to show.

    Blocking (it resolves the host): call it off the event loop. `ports=None` allows any port (tests only)."""
    url = (url or "").strip()
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("url is too long")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ValueError(f"url is not a valid address: {url!r}") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"url must start with http:// or https://, not {url!r}")
    if parts.username or parts.password:
        raise ValueError("url must not hold a user name or password")
    if ports is not None and port not in ports:
        raise ValueError("url may only use the standard web ports 80 and 443")
    host = parts.hostname
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            addresses = [str(info[4][0]) for info in resolver(host, None, type=socket.SOCK_STREAM)]
        except (OSError, UnicodeError):
            raise ValueError(f"the host of {url!r} could not be found") from None
    if not addresses or not all(allows_ip(address) for address in addresses):
        raise ValueError(f"{url!r} is not a public web address")
    return url
