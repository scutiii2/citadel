"""Where ConversationGateway and DecisionGateway are, and the token Legion calls each with.

Kept in Treasury (the database gateway), not in .env, so an admin sets them on
the Legion admin page. Every agent process reads the same record and caches it
for a short time, so an edit reaches all agents without a restart. The token is
write-only: `view()` reports only whether one is set.

Each service has its own record (`KEY` or `DECISION_KEY`, the `which` argument
below). Environment values (`CONVERSATION_GATEWAY_URL` / `DECISION_GATEWAY_URL`,
which the compose file sets, and the matching `..._TOKEN`) fill in whatever the
record does not hold, and are all Legion has while Treasury cannot be reached.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from src.runtime import internal_auth
from src.citadel_auth import AuthError, ServiceAuth, service_client

DEFAULT_URL = "http://127.0.0.1:29407"
INSTANCE = "legion"
CONNECTION = "data"
COLLECTION = "legion_settings"
KEY = "conversation_gateway"
DECISION_KEY = "decision_gateway"
# Record key -> (URL variable, token variable, URL used when nothing is set).
_SERVICES = {
    KEY: ("CONVERSATION_GATEWAY_URL", "CONVERSATION_GATEWAY_TOKEN", DEFAULT_URL),
    DECISION_KEY: ("DECISION_GATEWAY_URL", "DECISION_GATEWAY_TOKEN", "http://127.0.0.1:29406"),
}
MAX_TOKEN_LENGTH = 512

_TIMEOUT = httpx.Timeout(3.0)
_TTL_SECONDS = 30.0
# After a failed read, wait this long before asking Treasury again.
_RETRY_SECONDS = 10.0
# Tests replace these to answer without a network.
_TRANSPORT: httpx.AsyncBaseTransport | None = None
_SYNC_TRANSPORT: httpx.BaseTransport | None = None

# Record key -> (settings, monotonic time they stay fresh until).
_cache: "dict[str, tuple[GatewaySettings, float]]" = {}


class GatewaySettingsError(Exception):
    """A rejected or unsaved change; the message is safe to show."""


@dataclass(frozen=True)
class GatewaySettings:
    url: str
    token: str


def _record_url(which: str = KEY) -> str:
    base = (os.getenv("DB_GATEWAY_URL") or "http://127.0.0.1:29602").rstrip("/")
    return f"{base}/instances/{INSTANCE}/connections/{CONNECTION}/collections/{COLLECTION}/records/{which}"


def _headers() -> dict[str, str]:
    return {}


def _from_doc(doc: Any, which: str = KEY) -> GatewaySettings:
    """The record's values, with the environment filling the gaps."""
    doc = doc if isinstance(doc, dict) else {}
    url_env, token_env, default_url = _SERVICES[which]
    url = doc.get("url") or os.getenv(url_env) or default_url
    token = doc.get("token") or os.getenv(token_env) or ""
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


async def _read(which: str = KEY) -> dict[str, Any] | None:
    try:
        async with service_client(internal_auth.keyring, "treasury", transport=_TRANSPORT, timeout=_TIMEOUT) as client:
            return _doc(await client.get(_record_url(which), headers=_headers()))
    except (httpx.HTTPError, AuthError):
        return None


def _read_sync(which: str = KEY) -> dict[str, Any] | None:
    try:
        with httpx.Client(auth=ServiceAuth(internal_auth.keyring, "treasury"), transport=_SYNC_TRANSPORT, timeout=_TIMEOUT) as client:
            return _doc(client.get(_record_url(which), headers=_headers()))
    except (httpx.HTTPError, AuthError):
        return None


def _remember(doc: dict[str, Any] | None, which: str = KEY) -> GatewaySettings:
    """Cache what was read. A failed read keeps the last known values for a short while."""
    if doc is None:
        known = _cache[which][0] if which in _cache else _from_doc(None, which)
        _cache[which] = (known, time.monotonic() + _RETRY_SECONDS)
    else:
        _cache[which] = (_from_doc(doc, which), time.monotonic() + _TTL_SECONDS)
    return _cache[which][0]


def _fresh(which: str = KEY) -> GatewaySettings | None:
    cached = _cache.get(which)
    return cached[0] if cached and time.monotonic() < cached[1] else None


async def current(which: str = KEY) -> GatewaySettings:
    """The settings to use now (async callers: a streamed chat round)."""
    return _fresh(which) or _remember(await _read(which), which)


def current_sync(which: str = KEY) -> GatewaySettings:
    """The settings to use now (sync callers: interpret, decisions, the saved-gateway check)."""
    return _fresh(which) or _remember(_read_sync(which), which)


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


async def save(changes: dict[str, Any], which: str = KEY) -> GatewaySettings:
    """Store `changes` ({"url"?, "token"?}). A missing key keeps the stored value; an empty
    token clears it. Nothing is saved when a value is refused or Treasury cannot be reached."""
    unknown = set(changes) - {"url", "token"}
    if unknown:
        raise GatewaySettingsError(f"unknown setting: {', '.join(sorted(unknown))}")
    stored = await _read(which)
    if stored is None:
        raise GatewaySettingsError("Treasury is not reachable; the settings were not saved")
    doc = {key: stored[key] for key in ("url", "token") if stored.get(key)}
    if "url" in changes:
        doc["url"] = _checked_url(changes["url"])
    if "token" in changes:
        doc["token"] = _checked_token(changes["token"])
    try:
        async with service_client(internal_auth.keyring, "treasury", transport=_TRANSPORT, timeout=_TIMEOUT) as client:
            response = await client.put(_record_url(which), json={"doc": doc}, headers=_headers())
    except httpx.HTTPError as error:
        raise GatewaySettingsError("Treasury is not reachable; the settings were not saved") from error
    if response.status_code >= 400:
        raise GatewaySettingsError(f"Treasury refused the settings ({response.status_code})")
    return _remember(doc, which)


def view(settings: GatewaySettings) -> dict[str, Any]:
    """What the admin page shows. The token itself never leaves Legion."""
    return {"url": settings.url, "has_token": bool(settings.token)}


def reset_cache() -> None:
    _cache.clear()
