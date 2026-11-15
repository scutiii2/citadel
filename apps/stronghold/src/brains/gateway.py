"""Stronghold's private HTTP transport to Armory's deterministic brain operations."""

from __future__ import annotations

import httpx

from src.brains.connections import BrainError

_MINIMUM = "Safe promotion requires Obsidian Local REST API 5.2.0 or newer with conditional create support."


class BrainGateway:
    """`client` carries Armory's base URL."""

    def __init__(self, client: httpx.AsyncClient, token: str | None) -> None:
        self._client, self._token = client, token

    async def operation(self, uid: str, operation: str, scope: str, **arguments) -> dict:
        if not self._token or not uid:
            raise BrainError("Brain transport requires configured internal authentication", 503)
        try:
            response = await self._client.post(
                "/brains/operation", headers={"X-Internal-Token": self._token, "X-Requester-Uid": uid},
                json={"operation": operation, "scope": scope, **arguments}, timeout=30, follow_redirects=False)
        except httpx.HTTPError:
            raise BrainError("Brain service is unavailable", 503) from None
        if not response.is_success:
            # Armory exposes only safe errors; never include raw response bodies.
            try:
                if response.json().get("error") == _MINIMUM:
                    raise BrainError(_MINIMUM, 409)
            except (ValueError, AttributeError):
                pass
            raise BrainError("Brain operation failed. Check connection status and destination access.",
                             response.status_code if response.status_code in (403, 404, 409, 412) else 503)
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError:
            raise BrainError("Brain service returned an invalid response", 503) from None
