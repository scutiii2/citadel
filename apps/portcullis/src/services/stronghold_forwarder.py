"""Portcullis's one way into Stronghold.

Portcullis has already authenticated the account and checked its permission.
This sends the request on with the account's identity and the internal token.
The browser's cookies and headers are never forwarded: only what is built here
leaves, so Stronghold cannot see a session. Stronghold's own answers below 500
go back unchanged, so a route keeps the status and body Stronghold chose.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from src.models import Account
from src.services.traffic import TrafficRecorder

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class StrongholdUnavailable(Exception):
    """Stronghold could not be reached or answered 5xx (maps to 502)."""


@dataclass(frozen=True)
class ForwardedResponse:
    """Stronghold's answer, ready to hand back as it came."""

    status: int
    body: bytes
    content_type: str


class StrongholdForwarder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        internal_token: str | None,
        traffic: TrafficRecorder | None = None,
    ) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._internal_token = internal_token
        self._traffic = traffic or TrafficRecorder()

    def _headers(self, account: Account) -> dict[str, str]:
        headers = {"X-Requester-Username": account.username, "X-Requester-Email": account.email}
        if account.uid:
            headers["X-Requester-Uid"] = account.uid
        if self._internal_token:
            headers["X-Internal-Token"] = self._internal_token
        return headers

    async def forward(
        self,
        method: str,
        path: str,
        account: Account,
        *,
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> ForwardedResponse:
        """One call to a fixed Stronghold path. `path` is built by the route, never by the browser."""
        try:
            with self._traffic.timed("stronghold", f"{method} {path}") as timing:
                response = await self._client.request(
                    method,
                    f"{self._base}{path}",
                    params=params,
                    json=json,
                    headers=self._headers(account),
                    timeout=_TIMEOUT,
                )
                timing.ok = response.status_code < 500
        except httpx.HTTPError as error:
            logger.warning("stronghold %s %s unreachable: %s", method, path, error)
            raise StrongholdUnavailable(str(error)) from error
        if response.status_code >= 500:
            raise StrongholdUnavailable(f"stronghold answered {response.status_code}")
        return ForwardedResponse(
            response.status_code,
            response.content,
            response.headers.get("content-type", "application/json"),
        )
