"""What Stronghold asks Portcullis for: account facts, admin switches, email and the error log.

Portcullis owns accounts, settings, SMTP and logs. Requests arrive from it with the
requester's identity, but a background job (the calendar's alert scheduler) has no request,
so it asks here. Calls go to Portcullis's /internal routes with the shared internal token.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PlatformError(Exception):
    """Portcullis could not be reached or refused. The message is safe to log."""


class PortcullisClient:
    """`client` carries Portcullis's base URL and a timeout; the caller closes it."""

    def __init__(self, client: httpx.AsyncClient, internal_token: str | None) -> None:
        self._client = client
        self._headers = {"X-Internal-Token": internal_token} if internal_token else {}

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, headers=self._headers, **kwargs)
        except httpx.HTTPError as error:
            raise PlatformError(f"Portcullis is unreachable: {type(error).__name__}") from error

    async def recipient(self, uid: str, permission: str) -> dict[str, str] | None:
        """`{uid, email}` of an account that is active, verified and holds `permission`; else None."""
        response = await self._send("GET", f"/internal/accounts/{uid}/recipient", params={"permission": permission})
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PlatformError(f"Portcullis answered {response.status_code}")
        return response.json()

    async def permissions(self, uid: str) -> set[str] | None:
        """The permissions of an account that is active (and verified, when required); None for any other."""
        response = await self._send("GET", f"/internal/accounts/{uid}/permissions")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PlatformError(f"Portcullis answered {response.status_code}")
        return set(response.json()["permissions"])

    async def switches(self) -> dict[str, bool]:
        """The administrator's on/off settings, by name."""
        response = await self._send("GET", "/internal/switches")
        if response.status_code != 200:
            raise PlatformError(f"Portcullis answered {response.status_code}")
        return response.json()

    async def notify(self, uid: str, subject: str, body: str) -> None:
        """Email the account. Portcullis looks the address up; Stronghold never chooses it."""
        response = await self._send("POST", f"/internal/accounts/{uid}/notify", json={"subject": subject, "body": body})
        if response.status_code >= 400:
            raise PlatformError(f"Portcullis answered {response.status_code}")

    async def log_action(self, uid: str, action: str, message: str) -> None:
        """Add a line to the Logs page for something the account did. Never raises:
        the action already happened, and a lost log line must not turn it into an error."""
        try:
            response = await self._send("POST", f"/internal/accounts/{uid}/actions", json={"action": action, "message": message})
            if response.status_code >= 400:
                logger.warning("action log refused with status %s", response.status_code)
        except PlatformError as error:
            logger.warning("action log not delivered: %s", error)

    async def report_error(self, source: str, message: str) -> None:
        """Add a line to the administrators' Errors log. Never raises: reporting must not break the job."""
        try:
            await self._send("POST", "/internal/errors", json={"source": source, "message": message})
        except PlatformError as error:
            logger.warning("error report not delivered: %s", error)
