"""Which of an account's tickets have staff activity it has not read yet.

Armory owns the tickets and reports each one's `last_staff_activity_at`. Stronghold keeps only
when the account last opened each ticket: one document per account and ticket in the
"ticket_seen" collection (key `<uid>:<ticket id>`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.document_store import DocumentStore

COLLECTION = "ticket_seen"
_PAGE = 500
_PURGE_MAX_PAGES = 200


def _naive_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


class TicketUnread:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    async def _seen(self, owner: str) -> dict[int, datetime]:
        docs: list[dict] = []
        while True:
            page = await self._store.query(COLLECTION, {"owner": owner}, limit=_PAGE, offset=len(docs))
            docs += page
            if len(page) < _PAGE:
                break
        return {doc["ticket_id"]: datetime.fromisoformat(doc["last_seen_at"]) for doc in docs}

    async def unread_ids(self, owner: str, activity_times: dict[int, str | None]) -> set[int]:
        """Of these tickets (each with Armory's last staff activity time), the ones with newer activity than the account saw."""
        active = {ticket_id: _naive_utc(value) for ticket_id, value in activity_times.items() if value}
        if not active:
            return set()
        seen = await self._seen(owner)
        return {ticket_id for ticket_id, at in active.items() if ticket_id not in seen or at > seen[ticket_id]}

    async def mark_seen(self, owner: str, ticket_id: int, fetched_at: datetime) -> None:
        """A read covers activity before the fetch began, never a newer staff reply."""
        key = f"{owner}:{ticket_id}"
        existing = await self._store.get(COLLECTION, key)
        latest = max(fetched_at, datetime.fromisoformat(existing["last_seen_at"])) if existing else fetched_at
        await self._store.put(COLLECTION, key, {"key": key, "owner": owner, "ticket_id": ticket_id,
                                                "last_seen_at": latest.isoformat()})

    async def purge_owner(self, owner: str) -> int:
        """Delete every receipt of one account (used when the account is deleted). Returns the count."""
        removed = 0
        for _ in range(_PURGE_MAX_PAGES):
            docs = await self._store.query(COLLECTION, {"owner": owner}, limit=_PAGE)
            if not docs:
                break
            for doc in docs:
                removed += await self._store.delete(COLLECTION, doc["key"])
        return removed
