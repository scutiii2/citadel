"""Stronghold's client for Armory's ticket routes.

Only fixed paths are built here and every id is an int, so the browser never names a URL.
The requester's identity and the internal token go on every call. Armory's own 4xx
messages are kept (a TicketRefused); nothing here reads or logs ticket text.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from src.service_auth import authenticate
from src.citadel_auth import requester_header

from src.requester import Requester

logger = logging.getLogger(__name__)


class TicketUnavailable(Exception):
    """Armory could not be reached or answered 5xx (maps to 502)."""


class TicketRefused(Exception):
    """Armory answered 4xx; `message` is its own, safe to show."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _params(filters: dict[str, Any]) -> dict[str, str]:
    """Query values for Armory: None dropped, `possible` as "1", the rest as text."""
    params: dict[str, str] = {}
    for key, value in filters.items():
        if value is None or value is False:
            continue
        params[key] = "1" if value is True else str(value)
    return params


class ArmoryTickets:
    """`client` carries Armory's base URL; the caller closes it."""

    def __init__(self, client: httpx.AsyncClient, keyring=None) -> None:
        self._client = authenticate(client, "armory", keyring)

    def _headers(self, who: Requester) -> dict[str, str]:
        return requester_header()

    async def _request(self, method: str, path: str, who: Requester, *, params: dict[str, str] | None = None,
                       json: Any = None) -> Any:
        try:
            response = await self._client.request(method, path, params=params, json=json, headers=self._headers(who),
                                                  timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=False)
        except httpx.HTTPError as error:
            logger.warning("armory %s %s unreachable: %s", method, path, type(error).__name__)
            raise TicketUnavailable(type(error).__name__) from error
        if response.status_code == 204:
            return None
        try:
            body = response.json()
        except ValueError:
            body = None
        if 400 <= response.status_code < 500:
            message = body.get("error") if isinstance(body, dict) else None
            raise TicketRefused(response.status_code, str(message or f"armory answered {response.status_code}"))
        if response.status_code >= 500 or body is None:
            raise TicketUnavailable(f"armory answered {response.status_code}")
        return body

    # ---- reporter routes (the account's own tickets) ----------------------

    async def create(self, who: Requester, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/tickets", who, json=body)

    async def list_own(self, who: Requester, status: str | None = None) -> dict[str, Any]:
        return await self._request("GET", "/tickets", who, params=_params({"status": status, "all": True}))

    async def get_own(self, who: Requester, ticket_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/tickets/{int(ticket_id)}", who)

    async def comment_own(self, who: Requester, ticket_id: int, body: str) -> dict[str, Any]:
        return await self._request("POST", f"/tickets/{int(ticket_id)}/comments", who, json={"body": body})

    async def close_own(self, who: Requester, ticket_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/tickets/{int(ticket_id)}/close", who)

    async def reopen_own(self, who: Requester, ticket_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/tickets/{int(ticket_id)}/reopen", who)

    # ---- staff routes (everything) ----------------------------------------

    async def list_all(self, who: Requester, filters: dict[str, Any]) -> dict[str, Any]:
        return await self._request("GET", "/ticket-admin/tickets", who, params=_params(filters))

    async def get_any(self, who: Requester, ticket_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/ticket-admin/tickets/{int(ticket_id)}", who)

    async def update(self, who: Requester, ticket_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/ticket-admin/tickets/{int(ticket_id)}", who, json=changes)

    async def comment_staff(self, who: Requester, ticket_id: int, body: str) -> dict[str, Any]:
        return await self._request("POST", f"/ticket-admin/tickets/{int(ticket_id)}/comments", who, json={"body": body})

    async def move(self, who: Requester, ticket_id: int, group_id: int | None) -> dict[str, Any]:
        return await self._request("POST", f"/ticket-admin/tickets/{int(ticket_id)}/move", who, json={"group_id": group_id})

    async def list_groups(self, who: Requester, filters: dict[str, Any]) -> dict[str, Any]:
        return await self._request("GET", "/ticket-admin/groups", who, params=_params(filters))

    async def update_group(self, who: Requester, group_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/ticket-admin/groups/{int(group_id)}", who, json=changes)

    async def stats(self, who: Requester) -> dict[str, Any]:
        return await self._request("GET", "/ticket-admin/stats", who)
