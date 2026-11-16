"""Share links: read-only snapshots of a chat that anyone with the link may read.

One document per link in the "shared_chats" collection, keyed by the SHA-256 of the link's token.
The token is 256 random bits and only its hash is stored, so the raw link exists once, in the
response that creates it, and a leaked database leaks no working link. `messages` is the snapshot
Portcullis cut down to typed questions and plain answers; later changes to the chat never reach it.
Every account-side lookup filters by owner, so another account's id behaves like a missing one.
The public read answers "no such link" the same way for unknown, expired and revoked links.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.clock import utcnow
from src.document_store import DocumentStore
from src.schema.models import ShareDoc, checked

COLLECTION = "shared_chats"
MAX_ACTIVE_SHARES_PER_ACCOUNT = 50
TOKEN_BYTES = 32
_PAGE = 500
_PURGE_MAX_PAGES = 200


class ShareNotFound(Exception):
    """Unknown id, or another account's (deliberately indistinguishable)."""


class ShareLimitError(Exception):
    """The account is at its limit of active links."""


def hash_token(token: str) -> str:
    # A plain hash is enough: the token is 256 random bits, not a guessable password.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _active(doc: dict[str, Any], now: datetime) -> bool:
    return doc["expires_at"] is None or datetime.fromisoformat(doc["expires_at"]) > now


@dataclass(frozen=True)
class CreatedShare:
    share: dict[str, Any]
    # The link's secret. Not stored anywhere: this is the only time it exists.
    token: str


class ShareStore:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    async def _owned(self, owner: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        while True:
            page = await self._store.query(COLLECTION, {"owner": owner}, limit=_PAGE, offset=len(docs))
            docs += page
            if len(page) < _PAGE:
                return docs

    async def create(self, owner: str, chat_id: str, title: str, messages: list[dict[str, str]],
                     expires_in_days: int | None) -> CreatedShare:
        now = utcnow()
        owned = await self._owned(owner)
        for doc in owned:  # expired links are gone for good once the account makes a new one
            if not _active(doc, now):
                await self._store.delete(COLLECTION, doc["key"])
        active = [doc for doc in owned if _active(doc, now)]
        if len(active) >= MAX_ACTIVE_SHARES_PER_ACCOUNT:
            raise ShareLimitError(
                f"At most {MAX_ACTIVE_SHARES_PER_ACCOUNT} active shared links per account - revoke some first")
        taken = {doc["id"] for doc in active}
        share_id = secrets.randbelow(2**31 - 1) + 1
        while share_id in taken:
            share_id = secrets.randbelow(2**31 - 1) + 1
        token = secrets.token_urlsafe(TOKEN_BYTES)
        key = hash_token(token)
        doc = {
            "key": key, "id": share_id, "owner": owner, "chat_id": chat_id, "title": title,
            "messages": messages, "message_count": len(messages), "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=expires_in_days)).isoformat() if expires_in_days else None,
        }
        await self._store.put(COLLECTION, key, checked(ShareDoc, doc))
        return CreatedShare(doc, token)

    async def list(self, owner: str, chat_id: str | None = None) -> list[dict[str, Any]]:
        """Active links, newest first; expired ones are gone from the list."""
        now = utcnow()
        docs = [d for d in await self._owned(owner) if _active(d, now) and (chat_id is None or d["chat_id"] == chat_id)]
        return sorted(docs, key=lambda d: (d["created_at"], d["id"]), reverse=True)

    async def revoke(self, owner: str, share_id: int) -> dict[str, Any]:
        for doc in await self._owned(owner):
            if doc["id"] == share_id:
                await self._store.delete(COLLECTION, doc["key"])
                return doc
        raise ShareNotFound(share_id)

    async def revoke_chats(self, owner: str, chat_ids: list[str] | None) -> int:
        """Every link of these chats (None: of every chat) of one account. Returns the count."""
        removed = 0
        for doc in await self._owned(owner):
            if chat_ids is None or doc["chat_id"] in chat_ids:
                removed += await self._store.delete(COLLECTION, doc["key"])
        return removed

    async def read(self, token: str) -> dict[str, Any] | None:
        """The public read: the link's snapshot, or None for a link that is unknown, revoked or
        expired (callers must not say which)."""
        doc = await self._store.get(COLLECTION, hash_token(token))
        if doc is None:
            return None
        if not _active(doc, utcnow()):
            await self._store.delete(COLLECTION, doc["key"])
            return None
        return doc

    async def purge_owner(self, owner: str) -> int:
        """Delete every link of one account (used when the account is deleted). Returns the count."""
        removed = 0
        for _ in range(_PURGE_MAX_PAGES):
            docs = await self._store.query(COLLECTION, {"owner": owner}, limit=_PAGE)
            if not docs:
                break
            for doc in docs:
                removed += await self._store.delete(COLLECTION, doc["key"])
        return removed
