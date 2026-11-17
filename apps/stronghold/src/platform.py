"""What Stronghold asks Portcullis for: account facts and the logs.

Portcullis owns accounts, settings, SMTP and logs. Requests arrive from it with the
requester's identity; a job without a request asks here. Calls go to Portcullis's /internal routes with the shared internal token.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from src.service_auth import authenticate
from src.citadel_auth import verify_requester
from src import service_auth

logger = logging.getLogger(__name__)


class PlatformError(Exception):
    """Portcullis could not be reached or refused. The message is safe to log."""


class PortcullisClient:
    """`client` carries Portcullis's base URL and a timeout; the caller closes it."""

    def __init__(self, client: httpx.AsyncClient, keyring=None) -> None:
        self._keyring = keyring or service_auth.keyring
        self._client = authenticate(client, "portcullis", keyring)


    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, headers={}, **kwargs)
        except httpx.HTTPError as error:
            raise PlatformError(f"Portcullis is unreachable: {type(error).__name__}") from error

    async def permissions(self, uid: str) -> set[str] | None:
        """The permissions of an account that is active (and verified, when required); None for any other."""
        response = await self._send("GET", f"/internal/accounts/{uid}/permissions")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PlatformError(f"Portcullis answered {response.status_code}")
        return set(response.json()["permissions"])

    async def requester_token(self, uid: str) -> str:
        response = await self._send("POST", "/internal/requester-token", json={"uid": uid})
        if response.status_code != 200:
            raise PlatformError("Requester renewal refused")
        try:
            token = response.json()["token"]
            who = await verify_requester(self._keyring, token, "stronghold")
            if who.uid != uid:
                raise ValueError("requester mismatch")
            return token
        except (ValueError, KeyError, TypeError):
            raise PlatformError("Invalid requester renewal response") from None

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

    async def write_log(self, kind: str, uid: str, source: str, message: str,
                        details: str | None = None, prompts: str | None = None) -> None:
        """Add a line to the account's error or chat-trace log in Portcullis. Never raises: a lost
        log line must not break the chat turn being logged."""
        body = {"kind": kind, "uid": uid, "source": source, "message": message, "details": details, "prompts": prompts}
        try:
            response = await self._send("POST", "/internal/logs", json=body)
            if response.status_code >= 400:
                logger.warning("log line refused with status %s", response.status_code)
        except PlatformError as error:
            logger.warning("log line not delivered: %s", error)
