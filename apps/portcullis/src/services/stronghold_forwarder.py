"""Portcullis's one way into Stronghold.

Portcullis has already authenticated the account and checked its permission.
This sends the request on with the account's identity and signed service assertions.
The browser's cookies and headers are never forwarded: only what is built here
leaves, so Stronghold cannot see a session. Stronghold's own answers below 500
go back unchanged, so a route keeps the status and body Stronghold chose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from src.citadel_auth import Keyring, ServiceAuth
from src.services import service_auth

from src.models import Account
from src.services.traffic import TrafficRecorder
from src.services.uid_log_filter import redact

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_STACK_COMPACTION_TIMEOUT = httpx.Timeout(70.0, connect=10.0)
_STREAM_TIMEOUT = httpx.Timeout(60.0, connect=10.0, read=60.0)
# One upload is read, stored and perhaps parsed as a table or read by Reader before Stronghold answers.
_UPLOAD_TIMEOUT = httpx.Timeout(150.0, connect=10.0)
_UPLOAD_PATHS = frozenset(("/attachments/file", "/attachments/document"))
_CONNECTION_FEATURES = frozenset(("/bard/speak", "/bard/voices", "/attachments/audio",
                                  "/attachments/document", "/attachments/dictate", "/attachments/dictate/partial"))


class StrongholdUnavailable(Exception):
    """Stronghold could not be reached or answered 5xx (maps to 502)."""


@dataclass(frozen=True)
class ForwardedResponse:
    """Stronghold's answer, ready to hand back as it came."""

    status: int
    body: bytes
    content_type: str
    # Stronghold's own Retry-After (a 429 for a token limit), kept so the browser still sees it.
    retry_after: str | None = None


class StrongholdForwarder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        identity: Keyring | None,
        traffic: TrafficRecorder | None = None,
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._identity = identity or service_auth.keyring
        self._traffic = traffic or TrafficRecorder()

    def _headers(self, account: Account | None) -> dict[str, str]:
        if account is None:
            return {}
        return service_auth.identity_headers(account.username, account.email, account.uid, identity=self._identity)

    async def open_stream(
        self, path: str, account: Account | None, *, params: dict[str, str] | None = None, headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET a fixed Stronghold path as a stream the caller must close (the turn events, Bard audio). No read timeout:
        Stronghold sends a ping while idle, so a silent stream means it is gone. `headers` adds request headers (Range)."""
        try:
            request = self._client.build_request(
                "GET", f"{self._base}{path}", params=params, headers={**self._headers(account), **(headers or {})},
                timeout=_STREAM_TIMEOUT)
            return await self._client.send(request, stream=True, follow_redirects=False, auth=ServiceAuth(self._identity, "stronghold"))
        except httpx.HTTPError as error:
            logger.warning("stronghold GET %s unreachable: %s", redact(path), type(error).__name__)
            raise StrongholdUnavailable(type(error).__name__) from error

    async def forward(
        self,
        method: str,
        path: str,
        account: Account | None,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> ForwardedResponse:
        """One call to a fixed Stronghold path. `path` is built by the route, never by the browser."""
        stack = path.startswith("/stack/")
        brain = path.startswith("/brain/") or path == "/admin/brain-settings"
        if stack and path.endswith("/compact"):
            timeout = _STACK_COMPACTION_TIMEOUT
        elif path in _UPLOAD_PATHS:
            timeout = _UPLOAD_TIMEOUT
        else:
            timeout = _TIMEOUT
        try:
            # A purge path carries an account uid: keep it out of the traffic counters and the log.
            with self._traffic.timed("stronghold", f"{method} {redact(path)}") as timing:
                response = await self._client.request(
                    method,
                    f"{self._base}{path}",
                    params=params,
                    json=json,
                    headers=self._headers(account), auth=ServiceAuth(self._identity, "stronghold"),
                    timeout=timeout,
                    follow_redirects=False,  # the identity headers must never follow one
                )
                timing.ok = response.status_code < 500
        except httpx.HTTPError as error:
            logger.warning("stronghold %s %s unreachable: %s", method, redact(path), type(error).__name__)
            raise StrongholdUnavailable(type(error).__name__) from error
        # Routes whose 502 carries a detail that is safe and useful to show, such as a Treasury save refusal.
        tool_service = path in _CONNECTION_FEATURES or path in _UPLOAD_PATHS or path.startswith("/admin/tool-services/")
        safe_error = (tool_service and response.status_code == 502) or ((stack or brain) and response.status_code in {502, 503})
        if response.status_code >= 500 and not safe_error:
            raise StrongholdUnavailable(f"stronghold answered {response.status_code}")
        return ForwardedResponse(
            response.status_code,
            response.content,
            response.headers.get("content-type", "application/json"),
            response.headers.get("retry-after"),
        )
