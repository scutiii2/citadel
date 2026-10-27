# apps/Ember/ember_api/src/services/tuning_limits_service.py
"""Per-account response limits: how many tokens an answer may use and how many tool rounds it may take.

One document per account in treasury (collection "tuning_limits", key the account uid), like
nav_preferences. A missing field means "use the admin's value". legion applies them as
min(user, admin), so they can only lower what the admin allows."""

from __future__ import annotations

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "tuning_limits"
FIELDS = ("max_output_tokens", "max_tool_rounds")
# Same outer bounds legion's allowlist uses for these two keys.
BOUNDS = {"max_output_tokens": (1, 200_000), "max_tool_rounds": (1, 100)}


class TuningLimitsService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def get(self) -> dict[str, int]:
        doc = await self._store.get(COLLECTION, self._owner)
        if doc is None:
            return {}
        return {f: doc[f] for f in FIELDS if isinstance(doc.get(f), int) and not isinstance(doc.get(f), bool)}

    async def replace(self, limits: dict[str, int | None]) -> dict[str, int]:
        kept = {f: limits[f] for f in FIELDS if limits.get(f) is not None}
        if not kept:
            await self._store.delete(COLLECTION, self._owner)
            return {}
        await self._store.put(COLLECTION, self._owner, {
            "owner": self._owner, **kept, "updated_at": utcnow().isoformat(timespec="seconds"),
        })
        return kept

    async def reset(self) -> None:
        await self._store.delete(COLLECTION, self._owner)


async def purge_owner(store: DocumentStore, owner_uid: str) -> None:
    """Forget one account's limits (used when the account is deleted)."""
    await store.delete(COLLECTION, owner_uid)
