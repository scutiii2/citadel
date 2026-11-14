"""Where ConversationGateway is and the token Legion calls it with.

Kept in Treasury (the database gateway), not in .env, so an admin sets them on
the Legion admin page. Every agent process reads the same record and caches it
for a short time, so an edit reaches all agents without a restart. The token is
write-only: `view()` reports only whether one is set.

Environment values (`CONVERSATION_GATEWAY_URL`, which the compose file sets,
and `CONVERSATION_GATEWAY_TOKEN`) fill in whatever the record does not hold,
and are all Legion has while Treasury cannot be reached.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from src.runtime import internal_auth

DEFAULT_URL = "http://127.0.0.1:29407"
INSTANCE = "legion"
CONNECTION = "data"
COLLECTION = "legion_settings"
KEY = "conversation_gateway"
MAX_TOKEN_LENGTH = 512

_TIMEOUT = httpx.Timeout(3.0)
_TTL_SECONDS = 30.0
# After a failed read, wait this long before asking Treasury again.
_RETRY_SECONDS = 10.0
# Tests replace these to answer without a network.
_TRANSPORT: httpx.AsyncBaseTransport | None = None
_SYNC_TRANSPORT: httpx.BaseTransport | None = None

_cached: "GatewaySettings | None" = None
_cached_until = 0.0


class GatewaySettingsError(Exception):
    """A rejected or unsaved change; the message is safe to show."""


@dataclass(frozen=True)
class GatewaySettings:
    url: str
    token: str


def _record_url() -> str:
    base = (os.getenv("DB_GATEWAY_URL") or "http://127.0.0.1:29602").rstrip("/")
    return f"{base}/instances/{INSTANCE}/connections/{CONNECTION}/collections/{COLLECTION}/records/{KEY}"


def _headers() -> dict[str, str]:
    token = internal_auth.load_token()
    return {"X-Internal-Token": token} if token else {}


def _from_doc(doc: Any) -> GatewaySettings:
    """The record's values, with the environment filling the gaps."""
    doc = doc if isinstance(doc, dict) else {}
    url = doc.get("url") or os.getenv("CONVERSATION_GATEWAY_URL") or DEFAULT_URL
    token = doc.get("token") or os.getenv("CONVERSATION_GATEWAY_TOKEN") or ""
    return GatewaySettings(str(url).rstrip("/"), str(token))


def _doc(response: httpx.Response) -> dict[str, Any] | None:
    """The stored record; {} when there is none yet; None when Treasury did not answer usefully."""
    if response.status_code == 404:
        return {}
    if response.status_code != 200:
        return None
    try:
        doc = response.json().get("doc")
    except (ValueError, AttributeError):
        return None
    return doc if isinstance(doc, dict) else None


async def _read() -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(transport=_TRANSPORT, timeout=_TIMEOUT) as client:
            return _doc(await client.get(_record_url(), headers=_headers()))
    except httpx.HTTPError:
        return None


def _read_sync() -> dict[str, Any] | None:
    try:
        with httpx.Client(transport=_SYNC_TRANSPORT, timeout=_TIMEOUT) as client:
            return _doc(client.get(_record_url(), headers=_headers()))
    except httpx.HTTPError:
        return None


def _remember(doc: dict[str, Any] | None) -> GatewaySettings:
    """Cache what was read. A failed read keeps the last known values for a short while."""
    global _cached, _cached_until
    if doc is None:
        _cached = _cached or _from_doc(None)
        _cached_until = time.monotonic() + _RETRY_SECONDS
    else:
        _cached = _from_doc(doc)
        _cached_until = time.monotonic() + _TTL_SECONDS
    return _cached


def _fresh() -> GatewaySettings | None:
    return _cached if _cached is not None and time.monotonic() < _cached_until else None


async def current() -> GatewaySettings:
    """The settings to use now (async callers: a streamed chat round)."""
    return _fresh() or _remember(await _read())


def current_sync() -> GatewaySettings:
    """The settings to use now (sync callers: interpret, the saved-gateway check)."""
    return _fresh() or _remember(_read_sync())


def _checked_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatewaySettingsError("url must be an http(s) address")
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise GatewaySettingsError("url must be an http(s) address without credentials, query or fragment")
    return value.strip().rstrip("/")


def _checked_token(value: Any) -> str:
    if not isinstance(value, str) or len(value) > MAX_TOKEN_LENGTH or any(char.isspace() for char in value):
        raise GatewaySettingsError(f"token must be text without spaces, at most {MAX_TOKEN_LENGTH} characters")
    return value


async def save(changes: dict[str, Any]) -> GatewaySettings:
    """Store `changes` ({"url"?, "token"?}). A missing key keeps the stored value; an empty
    token clears it. Nothing is saved when a value is refused or Treasury cannot be reached."""
    unknown = set(changes) - {"url", "token"}
    if unknown:
        raise GatewaySettingsError(f"unknown setting: {', '.join(sorted(unknown))}")
    stored = await _read()
    if stored is None:
        raise GatewaySettingsError("Treasury is not reachable; the settings were not saved")
    doc = {key: stored[key] for key in ("url", "token") if stored.get(key)}
    if "url" in changes:
        doc["url"] = _checked_url(changes["url"])
    if "token" in changes:
        doc["token"] = _checked_token(changes["token"])
    try:
        async with httpx.AsyncClient(transport=_TRANSPORT, timeout=_TIMEOUT) as client:
            response = await client.put(_record_url(), json={"doc": doc}, headers=_headers())
    except httpx.HTTPError as error:
        raise GatewaySettingsError("Treasury is not reachable; the settings were not saved") from error
    if response.status_code >= 400:
        raise GatewaySettingsError(f"Treasury refused the settings ({response.status_code})")
    return _remember(doc)


def view(settings: GatewaySettings) -> dict[str, Any]:
    """What the admin page shows. The token itself never leaves Legion."""
    return {"url": settings.url, "has_token": bool(settings.token)}


def reset_cache() -> None:
    global _cached, _cached_until
    _cached, _cached_until = None, 0.0
