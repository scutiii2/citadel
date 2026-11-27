"""Armory's hold routes, called as the Stronghold service with the account in the body."""

from __future__ import annotations

import httpx

from src.service_auth import authenticate

_TIMEOUT = 30.0


class HoldsUnreachable(Exception):
    """Armory did not answer; nothing else will get through either."""


class HoldNotAccepted(Exception):
    """Armory answered but could not take the call now: retry it."""


class HoldRefused(Exception):
    """Armory says the call itself is wrong: retrying cannot help."""


class ArmoryHolds:
    def __init__(self, client: httpx.AsyncClient, keyring=None) -> None:
        self._client = authenticate(client, "armory", keyring)

    async def hold(self, uid: str, chat_id: str, file_ids: list[str]) -> None:
        await self._post("/holds", {"uid": uid, "chat_id": chat_id, "file_ids": file_ids})

    async def release(self, uid: str, chat_ids: list[str]) -> None:
        await self._post("/holds/release", {"uid": uid, "chat_ids": chat_ids})

    async def release_all(self, uid: str) -> None:
        await self._post("/holds/release", {"uid": uid, "all": True})

    async def _post(self, path: str, body: dict) -> None:
        try:
            response = await self._client.post(path, json=body, timeout=_TIMEOUT, follow_redirects=False)
        except httpx.HTTPError as error:
            raise HoldsUnreachable(error.__class__.__name__) from error
        if response.status_code in (400, 422):
            raise HoldRefused(f"armory answered {response.status_code}")
        if response.status_code != 200:  # an older Armory without the route answers 404
            raise HoldNotAccepted(f"armory answered {response.status_code}")
