"""Per-account response limits: how many tokens an answer may use and how many tool rounds it may take.

One document per account in Treasury (collection "tuning_limits", key the account uid). A missing
field means "use the admin's value". Legion applies them as min(user, admin), so they can only
lower what the admin allows. The admin's values are Legion's own tuning, read through `LegionTuning`.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from src.agents.directory import AgentDirectory
from src.clock import utcnow
from src.document_store import DocumentStore
from src.requester import Requester

COLLECTION = "tuning_limits"
FIELDS = ("max_output_tokens", "max_tool_rounds")
# The outer bounds Legion's allowlist uses for these two keys.
BOUNDS = {"max_output_tokens": (1, 200_000), "max_tool_rounds": (1, 100)}


class LimitsStore:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    async def get(self, uid: str) -> dict[str, int]:
        doc = await self._store.get(COLLECTION, uid)
        if doc is None:
            return {}
        return {f: doc[f] for f in FIELDS if isinstance(doc.get(f), int) and not isinstance(doc.get(f), bool)}

    async def replace(self, uid: str, limits: dict[str, int | None]) -> dict[str, int]:
        kept = {f: limits[f] for f in FIELDS if limits.get(f) is not None}
        if not kept:
            await self._store.delete(COLLECTION, uid)
            return {}
        await self._store.put(COLLECTION, uid, {"owner": uid, **kept, "updated_at": utcnow().isoformat(timespec="seconds")})
        return kept

    async def reset(self, uid: str) -> None:
        await self._store.delete(COLLECTION, uid)


class LegionUnavailable(Exception):
    """No agent is running, or Legion did not give a usable answer."""


class LegionTuning:
    """Reads Legion's tuning (`GET /agents/tuning`) from the entry agent, else any running one.

    Only this fixed path is built here; the browser never names a URL."""

    def __init__(self, client: httpx.AsyncClient, directory: AgentDirectory, token: str | None) -> None:
        self._client, self._directory, self._token = client, directory, token

    async def ceiling(self, who: Requester) -> dict[str, Any]:
        """Legion's current default token limits, which an account's own limits cannot exceed."""
        agent = await self._directory.entry() or next(iter(await self._directory.all()), None)
        if agent is None:
            raise LegionUnavailable("No agent is running")
        parts = urlsplit(agent.url)
        url = urlunsplit((parts.scheme, parts.netloc, "/agents/tuning", "", ""))
        headers = {"X-Requester-Username": who.username, "X-Requester-Email": who.email, "X-Requester-Uid": who.uid}
        if self._token:
            headers["X-Internal-Token"] = self._token
        try:
            response = await self._client.get(url, headers=headers, timeout=15.0, follow_redirects=False)
            default = response.json()["effective"]["token_limits"]["default"] if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise LegionUnavailable(type(error).__name__) from error
        if not isinstance(default, dict):
            raise LegionUnavailable(f"legion answered {response.status_code}")
        return default
