"""Bounded manifest fetching and game URL validation.

DNS hostnames are allowed without resolution, as specified by the plan; these
checks cannot prove a DNS target public or prevent DNS rebinding. Production
must also restrict outbound network access to trusted game hosts.
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
import httpx
from src.services.permissions import GAME_ID_PATTERN


class ManifestError(Exception):
    """Safe manifest validation or connection error for the registering account."""


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    description: str
    icon: str
    version: str
    raw: dict


class GameUrlPolicy:
    def __init__(self, *, allow_private: bool) -> None:
        self._allow_private = allow_private

    def normalize(self, raw: str) -> str:
        if not isinstance(raw, str) or any(ord(c) < 33 or ord(c) == 127 for c in raw) or "\\" in raw:
            raise ManifestError("Invalid game URL")
        try:
            parts = urlsplit(raw)
            host, port = parts.hostname, parts.port
        except ValueError as error:
            raise ManifestError("Invalid game URL") from error
        if parts.scheme not in ("http", "https") or not host or parts.username is not None or parts.password is not None:
            raise ManifestError("Use an http or https URL without credentials")
        host = host.lower().rstrip(".")
        if not host or "%" in host:
            raise ManifestError("Invalid game host")
        private = host == "localhost" or host.endswith(".localhost")
        try:
            address = ipaddress.ip_address(host)
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            private = private or not address.is_global or address.is_multicast
        except ValueError:
            pass  # DNS hostnames are allowed; see module docstring.
        if private and not self._allow_private:
            raise ManifestError("Private game URLs are disabled")
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        result = urlunsplit((parts.scheme, authority, parts.path.rstrip("/"), "", ""))
        if len(result) > 1000:
            raise ManifestError("The game URL is too long")
        return result


def normalize_game_url(raw: str, *, allow_private: bool) -> str:
    """Keep a subpath base; remove query, fragment and trailing slashes.

    DNS names are permitted without resolution; literal non-public IPs and
    localhost names require allow_private. See the module's DNS limitation.
    """
    return GameUrlPolicy(allow_private=allow_private).normalize(raw)


class ManifestFetcher:
    def __init__(self, client: httpx.AsyncClient, *, allow_private: bool, timeout: float = 5.0, max_bytes: int = 65536) -> None:
        self._client = client
        self._policy = GameUrlPolicy(allow_private=allow_private)
        self._timeout = timeout
        self._max_bytes = max_bytes

    async def fetch(self, base_url: str) -> Manifest:
        base = self._policy.normalize(base_url)
        try:
            async with self._client.stream("GET", f"{base}/manifest.json", timeout=self._timeout, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ManifestError(f"The game answered {response.status_code} for its manifest")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > self._max_bytes:
                        raise ManifestError("The manifest is too large")
                    body.extend(chunk)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise ManifestError("Cannot reach the game") from error
        return self._parse(bytes(body))

    @staticmethod
    def _parse(body: bytes) -> Manifest:
        try:
            raw = json.loads(body)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ManifestError("The manifest must be JSON") from error
        if not isinstance(raw, dict):
            raise ManifestError("The manifest must be an object")
        game_id = raw.get("id")
        if not isinstance(game_id, str) or not re.fullmatch(GAME_ID_PATTERN, game_id):
            raise ManifestError("Invalid manifest id")
        values = {}
        for field, limit in (("name", 80), ("description", 300), ("icon", 300), ("version", 40)):
            value = raw.get(field, "")
            if not isinstance(value, str) or len(value) > limit or (field == "name" and not value.strip()):
                raise ManifestError(f"Invalid manifest {field}")
            values[field] = value
        return Manifest(id=game_id, raw=raw, **values)
