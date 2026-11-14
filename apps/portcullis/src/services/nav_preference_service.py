"""Per-account nav rail arrangement: page order, pinned pages, hidden pages.

Stored as one document per account in db_gateway (collection "nav_preferences", key the
account uid). The service holds only ids and does not know which pages exist; it keeps the
lists small and consistent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "nav_preferences"
MAX_PAGES = 50
PAGE_ID_MAX = 64


@dataclass(frozen=True)
class NavLayout:
    order: list[str] = field(default_factory=list)
    pinned: list[str] = field(default_factory=list)
    hidden: list[str] = field(default_factory=list)


def _unique(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def normalize(layout: NavLayout) -> NavLayout:
    """Drops repeats; pinned and hidden may only name pages in the order, and a
    page cannot be both (hiding wins, since a hidden page is not in the rail)."""
    order = _unique(layout.order)
    known = set(order)
    hidden = [p for p in _unique(layout.hidden) if p in known]
    pinned = [p for p in _unique(layout.pinned) if p in known and p not in hidden]
    return NavLayout(order=order, pinned=pinned, hidden=hidden)


class NavPreferenceService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def get(self) -> NavLayout:
        doc = await self._store.get(COLLECTION, self._owner)
        if doc is None:
            return NavLayout()
        return NavLayout(order=list(doc["order"]), pinned=list(doc["pinned"]), hidden=list(doc["hidden"]))

    async def replace(self, layout: NavLayout) -> NavLayout:
        layout = normalize(layout)
        doc = {
            "owner": self._owner, "order": layout.order, "pinned": layout.pinned, "hidden": layout.hidden,
            "updated_at": utcnow().isoformat(timespec="seconds"),
        }
        await self._store.put(COLLECTION, self._owner, doc)
        return layout

    async def reset(self) -> None:
        await self._store.delete(COLLECTION, self._owner)


async def purge_owner(store: DocumentStore, owner_uid: str) -> None:
    """Forget one account's arrangement (used when the account is deleted)."""
    await store.delete(COLLECTION, owner_uid)
