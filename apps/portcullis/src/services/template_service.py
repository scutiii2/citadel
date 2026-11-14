"""Per-account prompt templates, stored as documents in db_gateway.

One document per template in the "prompt_templates" collection. The key is the owner's uid plus
a hash of the name folded to lower case, so "Review" and "review" are the same key and the
gateway's create-if-absent keeps names unique even when two requests race. `id` is a random
hex string the browser uses to address the template; `owner` is the account's uid. Another
account's id behaves exactly like a nonexistent one.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "prompt_templates"
MAX_TEMPLATES_PER_ACCOUNT = 100
NAME_MAX = 60
BODY_MAX = 10_000
TEMPLATE_ID_PATTERN = r"^[0-9a-f]{32}$"
_TEMPLATE_ID = re.compile(TEMPLATE_ID_PATTERN)
_PURGE_PAGE = 500
_PURGE_MAX_PAGES = 20


class TemplateNotFound(Exception):
    """Unknown id, or another account's (deliberately indistinguishable)."""


class TemplateNameTaken(Exception):
    """The account already has a template with this name (ignoring case)."""


class TemplateLimitError(Exception):
    """The account is at its template limit."""


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Template:
        return cls(
            doc["id"], doc["name"], doc["body"],
            datetime.fromisoformat(doc["created_at"]), datetime.fromisoformat(doc["updated_at"]),
        )


def _name_key(name: str) -> str:
    return name.casefold()


def _key(owner_uid: str, name: str) -> str:
    # Hashed: a name may hold characters that are not allowed in a document key (Firestore: "/").
    return f"{owner_uid}:{hashlib.sha256(_name_key(name).encode()).hexdigest()[:32]}"


class TemplateService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def _docs(self) -> list[dict[str, Any]]:
        return await self._store.query(COLLECTION, {"owner": self._owner}, limit=MAX_TEMPLATES_PER_ACCOUNT + 1)

    async def list(self) -> list[Template]:
        """Most recently edited first."""
        docs = sorted(await self._docs(), key=lambda d: (d["updated_at"], d["id"]), reverse=True)
        return [Template.from_doc(d) for d in docs]

    async def create(self, name: str, body: str) -> Template:
        if len(await self._docs()) >= MAX_TEMPLATES_PER_ACCOUNT:
            raise TemplateLimitError(f"At most {MAX_TEMPLATES_PER_ACCOUNT} templates per account - delete some first")
        now = utcnow().isoformat()
        doc = {
            "id": uuid.uuid4().hex, "owner": self._owner, "name": name, "name_key": _name_key(name),
            "body": body, "created_at": now, "updated_at": now,
        }
        if not await self._store.create(COLLECTION, _key(self._owner, name), doc):
            raise TemplateNameTaken(name)
        return Template.from_doc(doc)

    async def update(self, template_id: str, name: str, body: str) -> Template:
        old_key, doc = await self._find(template_id)
        new_key = _key(self._owner, name)
        doc.update(name=name, name_key=_name_key(name), body=body, updated_at=utcnow().isoformat())
        if new_key == old_key:
            await self._store.put(COLLECTION, new_key, doc)
        else:  # renamed to a different name: claim the new key first, then free the old one
            if not await self._store.create(COLLECTION, new_key, doc):
                raise TemplateNameTaken(name)
            await self._store.delete(COLLECTION, old_key)
        return Template.from_doc(doc)

    async def delete(self, template_id: str) -> None:
        key, _doc = await self._find(template_id)
        await self._store.delete(COLLECTION, key)

    async def _find(self, template_id: str) -> tuple[str, dict[str, Any]]:
        if not _TEMPLATE_ID.fullmatch(template_id):
            raise TemplateNotFound(template_id)
        for doc in await self._docs():
            if doc["id"] == template_id:
                return _key(self._owner, doc["name"]), doc
        raise TemplateNotFound(template_id)


async def purge_owner(store: DocumentStore, owner_uid: str) -> int:
    """Delete every template of one account (used when the account is deleted). Returns the count."""
    removed = 0
    for _ in range(_PURGE_MAX_PAGES):
        docs = await store.query(COLLECTION, {"owner": owner_uid}, limit=_PURGE_PAGE)
        if not docs:
            break
        for doc in docs:
            removed += await store.delete(COLLECTION, _key(owner_uid, doc["name"]))
    return removed
