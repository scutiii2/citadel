"""Per-account notes, stored as documents in db_gateway (not in ember_api's database).

One document per note in the "notes" collection, keyed by a random id. `owner` is the
account's uid (never reused). A note is only ever returned to its owner: anyone else's
id is reported as not found, the same as an id that does not exist.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "notes"
MAX_NOTES = 200
TITLE_MAX = 200
BODY_MAX = 20_000
TAG_MAX = 30
MAX_TAGS = 10
_NOTE_ID = re.compile(r"[0-9a-f]{32}")
_TAG = re.compile(r"[a-z0-9][a-z0-9_-]*")
_PURGE_PAGE = 500
_PURGE_MAX_PAGES = 20


class NoteNotFound(Exception):
    pass


class NoteLimit(Exception):
    pass


def normalize_tags(raw: list[str]) -> list[str]:
    """Trimmed, lowercase tags without repeats, in the order given. Raises ValueError
    for a tag that is empty, too long or has characters other than a-z, 0-9, - and _."""
    tags: list[str] = []
    for item in raw:
        tag = item.strip().lower()
        if not tag or len(tag) > TAG_MAX or not _TAG.fullmatch(tag):
            raise ValueError(f"A tag is 1 to {TAG_MAX} characters: letters, digits, - and _")
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"A note can have at most {MAX_TAGS} tags")
    return tags


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    created_at: str
    updated_at: str
    tags: tuple[str, ...] = ()
    agent_readable: bool = False

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Note:
        # Notes saved before tags and the agent flag existed have neither: no tags, agents locked out.
        return cls(
            doc["id"], doc["title"], doc["body"], doc["created_at"], doc["updated_at"],
            tuple(doc.get("tags") or ()), doc.get("agent_readable") is True,
        )


class NotesService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def list(self) -> list[Note]:
        docs = await self._store.query(COLLECTION, {"owner": self._owner}, limit=MAX_NOTES)
        return sorted((Note.from_doc(d) for d in docs), key=lambda n: n.updated_at, reverse=True)

    async def get(self, note_id: str) -> Note:
        return Note.from_doc(await self._owned(note_id))

    async def tags(self) -> list[tuple[str, int]]:
        """Every tag the account uses with its note count: most used first, then by name."""
        counts = Counter(tag for note in await self.list() for tag in note.tags)
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))

    async def create(
        self, title: str, body: str, tags: list[str] | None = None, agent_readable: bool = False
    ) -> Note:
        if len(await self._store.query(COLLECTION, {"owner": self._owner}, limit=MAX_NOTES)) >= MAX_NOTES:
            raise NoteLimit(f"You can keep at most {MAX_NOTES} notes")
        now = _now()
        doc = {
            "id": uuid.uuid4().hex, "owner": self._owner, "title": title, "body": body,
            "tags": list(tags or []), "agent_readable": agent_readable,
            "created_at": now, "updated_at": now,
        }
        await self._store.put(COLLECTION, doc["id"], doc)
        return Note.from_doc(doc)

    async def update(
        self, note_id: str, title: str, body: str, tags: list[str] | None = None, agent_readable: bool = False
    ) -> Note:
        doc = await self._owned(note_id)
        doc.update(title=title, body=body, tags=list(tags or []), agent_readable=agent_readable, updated_at=_now())
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
