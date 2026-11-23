"""Where ConversationGateway and DecisionGateway are, and the token Legion calls each with.

Kept in Treasury (the database gateway), not in .env, so an admin sets them on
the Legion admin page. Every agent process reads the same record and caches it
for a short time, so an edit reaches all agents without a restart. The token is
write-only: `view()` reports only whether one is set.

Each service has its own record (`KEY` or `DECISION_KEY`, the `which` argument
below). Whatever the record does not hold is the default address and no token, and
that is all Legion has while Treasury cannot be reached. No environment variable
names a gateway.

Where Treasury itself is: `treasury_address()`, from TREASURY_URL or tracked config_app.json.
"""

from __future__ import annotations

import asyncio
import json
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
# Record key -> the URL used when the record holds none.
_SERVICES = {
    KEY: DEFAULT_URL,
    DECISION_KEY: "http://127.0.0.1:29406",
}
DEFAULT_TREASURY_URL = "http://127.0.0.1:29602"
MAX_TOKEN_LENGTH = 512
MAX_DESCRIPTION_LENGTH = 500
_save_locks = {key: asyncio.Lock() for key in _SERVICES}

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
    description: str = ""


def treasury_address() -> str:
    """The only bootstrap address: TREASURY_URL, config_app.json, then local default."""
    from src.runtime import config_files

    override = os.getenv("TREASURY_URL")
    if override:
        return override.strip().rstrip("/")
    path = config_files.CONFIGS_DIR / "config_app.json"
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return str(raw.get("treasury_url") or DEFAULT_TREASURY_URL).strip().rstrip("/")


def _record_url(which: str = KEY) -> str:
    base = treasury_address()
    return f"{base}/instances/{INSTANCE}/connections/{CONNECTION}/collections/{COLLECTION}/records/{which}"


def _headers() -> dict[str, str]:
    return {}


def _from_doc(doc: Any, which: str = KEY) -> GatewaySettings:
    """The record's values, with the default address filling the gap."""
    doc = doc if isinstance(doc, dict) else {}
    url = doc.get("url") or _SERVICES[which]
    token = doc.get("token") or ""
    description = doc.get("description")
    return GatewaySettings(str(url).rstrip("/"), str(token), description if isinstance(description, str) else "")


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


def last_known(which: str = KEY) -> GatewaySettings:
    """Return cached settings or defaults without contacting Treasury."""
    cached = _cache.get(which)
    return cached[0] if cached else _from_doc(None, which)


async def current(which: str = KEY) -> GatewaySettings:
    """The settings to use now (async callers: a streamed chat round)."""
    return _fresh(which) or _remember(await _read(which), which)


def current_sync(which: str = KEY) -> GatewaySettings:
    """The settings to use now (sync callers: interpret, decisions, the saved-gateway check)."""
    return _fresh(which) or _remember(_read_sync(which), which)


def _checked_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatewaySettingsError("url must be an http(s) address")
    try:
        parts = urlsplit(value.strip())
        _ = parts.port
    except ValueError as error:
        raise GatewaySettingsError("url must be an http(s) address with a valid host and port") from error
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise GatewaySettingsError("url must be an http(s) address without credentials, query or fragment")
    return value.strip().rstrip("/")


def _checked_token(value: Any) -> str:
    if not isinstance(value, str) or len(value) > MAX_TOKEN_LENGTH or any(char.isspace() for char in value):
        raise GatewaySettingsError(f"token must be text without spaces, at most {MAX_TOKEN_LENGTH} characters")
    return value


def _checked_description(value: Any) -> str:
    if not isinstance(value, str) or len(value.strip()) > MAX_DESCRIPTION_LENGTH:
        raise GatewaySettingsError(f"description must be text, at most {MAX_DESCRIPTION_LENGTH} characters")
    return value.strip()


async def save(changes: dict[str, Any], which: str = KEY) -> GatewaySettings:
    """Merge a partial edit into one Treasury record. Empty text clears description or token."""
    validators = {"url": _checked_url, "token": _checked_token, "description": _checked_description}
    unknown = changes.keys() - validators.keys()
    if unknown:
        raise GatewaySettingsError(f"unknown setting: {', '.join(sorted(unknown))}")
    patch = {key: validators[key](value) for key, value in changes.items()}
    # Treasury replaces the full record. Serialize concurrent partial writes per gateway.
    async with _save_locks[which]:
        stored = await _read(which)
        if stored is None:
            raise GatewaySettingsError("Treasury is not reachable; the settings were not saved")
        doc = {**stored, **patch}
        try:
            async with service_client(internal_auth.keyring, "treasury", transport=_TRANSPORT, timeout=_TIMEOUT) as client:
                response = await client.put(_record_url(which), json={"doc": doc}, headers=_headers())
        except (httpx.HTTPError, AuthError) as error:
            raise GatewaySettingsError("Treasury is not reachable; the settings were not saved") from error
        if not response.is_success:
            raise GatewaySettingsError(f"Treasury refused the settings ({response.status_code})")
        return _remember(doc, which)


def view(settings: GatewaySettings) -> dict[str, Any]:
    """What the admin page shows. The token itself never leaves Legion."""
    return {"url": settings.url, "description": settings.description, "has_token": bool(settings.token)}


def reset_cache() -> None:
    _cache.clear()
