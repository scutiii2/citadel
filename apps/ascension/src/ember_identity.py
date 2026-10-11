"""Redeem one-time launch tickets with Ember, server to server."""
from __future__ import annotations
import httpx


class IdentityUnavailable(Exception):
    """Ember could not supply a usable identity response."""


class EmberIdentity:
    def __init__(self, client: httpx.AsyncClient, base_url: str, token: str, game_id: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._game_id = game_id

    async def redeem(self, ticket: str) -> str | None:
        try:
            response = await self._client.post(
                f"{self._base_url}/internal/games/tickets/redeem",
                json={"ticket": ticket, "game_id": self._game_id},
                headers={"X-Internal-Token": self._token}, timeout=5.0, follow_redirects=False,
            )
            if response.status_code == 401:
                return None
            if response.status_code != 200:
                raise IdentityUnavailable()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise IdentityUnavailable() from error
        if not isinstance(payload, dict) or not isinstance(payload.get("account_id"), str) or not payload["account_id"]:
            raise IdentityUnavailable()
        return payload["account_id"]
