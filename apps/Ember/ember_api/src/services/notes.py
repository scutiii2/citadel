"""Per-account notes, stored as documents in db_gateway (not in ember_api's database).

One document per note in the "notes" collection, keyed by a random id. `owner` is the
account's uid (never reused). A note is only ever returned to its owner: anyone else's
id is reported as not found, the same as an id that does not exist.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "notes"
MAX_NOTES = 200
TITLE_MAX = 200
BODY_MAX = 20_000
_NOTE_ID = re.compile(r"[0-9a-f]{32}")
_PURGE_PAGE = 500
_PURGE_MAX_PAGES = 20


class NoteNotFound(Exception):
    pass


class NoteLimit(Exception):
    pass


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    created_at: str
    updated_at: str

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Note:
        return cls(doc["id"], doc["title"], doc["body"], doc["created_at"], doc["updated_at"])


class NotesService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def list(self) -> list[Note]:
        docs = await self._store.query(COLLECTION, {"owner": self._owner}, limit=MAX_NOTES)
        return sorted((Note.from_doc(d) for d in docs), key=lambda n: n.updated_at, reverse=True)

    async def get(self, note_id: str) -> Note:
        return Note.from_doc(await self._owned(note_id))

    async def create(self, title: str, body: str) -> Note:
        if len(await self._store.query(COLLECTION, {"owner": self._owner}, limit=MAX_NOTES)) >= MAX_NOTES:
            raise NoteLimit(f"You can keep at most {MAX_NOTES} notes")
        now = _now()
        doc = {
            "id": uuid.uuid4().hex, "owner": self._owner, "title": title, "body": body,
            "created_at": now, "updated_at": now,
        }
        await self._store.put(COLLECTION, doc["id"], doc)
        return Note.from_doc(doc)

    async def update(self, note_id: str, title: str, body: str) -> Note:
        doc = await self._owned(note_id)
        doc.update(title=title, body=body, updated_at=_now())
        await self._store.put(COLLECTION, note_id, doc)
        return Note.from_doc(doc)

    async def delete(self, note_id: str) -> None:
        await self._owned(note_id)
        await self._store.delete(COLLECTION, note_id)

    async def _owned(self, note_id: str) -> dict[str, Any]:
        doc = await self._store.get(COLLECTION, note_id) if _NOTE_ID.fullmatch(note_id) else None
        if doc is None or doc.get("owner") != self._owner:
            raise NoteNotFound(note_id)
        return doc


async def purge_owner(store: DocumentStore, owner_uid: str) -> int:
    """Delete every note of one account (used when the account is deleted). Returns the count."""
    removed = 0
    for _ in range(_PURGE_MAX_PAGES):
        docs = await store.query(COLLECTION, {"owner": owner_uid}, limit=_PURGE_PAGE)
        if not docs:
            break
        for doc in docs:
            removed += await store.delete(COLLECTION, doc["id"])
    return removed


def _now() -> str:
    return utcnow().isoformat(timespec="seconds")
