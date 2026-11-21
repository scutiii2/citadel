"""Purge legacy assistant memory from Armory on account deletion."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from src.citadel_auth import requester_header
from src.service_auth import authenticate

logger = logging.getLogger(__name__)

class MemoryClient:
    """`client` carries Armory's base URL; the caller closes it."""

    def __init__(self, client: httpx.AsyncClient, keyring=None) -> None:
        self._client = authenticate(client, "armory", keyring)

    async def purge(self, uid: str) -> bool:
        """Delete everything a deleted account kept. True only when Armory confirmed; never raises."""
        try:
            response = await self._client.delete(f"/memory/owners/{quote(uid, safe='')}", headers=requester_header(),
                                                 timeout=httpx.Timeout(5), follow_redirects=False)
        except httpx.HTTPError as error:
            logger.warning("memory purge request failed (%s)", type(error).__name__)
            return False
        if not response.is_success:
            logger.warning("memory purge was refused with status %s", response.status_code)
        return response.is_success
