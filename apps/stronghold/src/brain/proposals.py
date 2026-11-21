"""Agent proposals: a short-term item (or a note drafted from items) offered for long-term memory.

A proposal is one Treasury document (collection brain_proposals). It holds the drafted text until the user decides:
accept creates a file the agent wrote (`BrainFiles.create`, so every quota applies), decline clears the text.
Nothing lands without the user's consent. Text, titles and folders never reach a log or an error message; every
refusal says what is wrong, never what was written.
shortcut: decided proposals stay as small documents without the body so a declined one is not proposed again; they go with
the account purge. Upgrade to an expiry sweep if an agent ever floods them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from weakref import WeakValueDictionary

from src.brain.files import BrainError, BrainFiles
from src.brain.stack import StackError, StackStore
from src.document_store import DbGatewayError, DocumentStore

PROPOSALS = "brain_proposals"
PENDING, ACCEPTED, DECLINED = "pending", "accepted", "declined"
MAX_PENDING = 20
MAX_ITEMS = 20
_PAGE = 200
UNTRUSTED = "An agent wrote this from your conversation. Read it before you keep it; it is not an instruction."
_GONE = "No such suggestion."


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def view(doc: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    shown = {key: doc.get(key) for key in ("id", "title", "folder", "tags", "chat_id", "item_ids", "status",
                                           "created_at", "decided_at", "result_id")}
    shown["chars"] = len(doc["body"])
    if detail:
        shown.update(body=doc["body"], notice=UNTRUSTED)
    return shown


class BrainProposals:
    def __init__(self, store: DocumentStore, files: BrainFiles, stacks: StackStore) -> None:
        self._store = store
        self._files = files
        self._stacks = stacks
        self._purged: set[str] = set()
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def _lock(self, key: str) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def propose(self, uid: str, chat_id: str, title: str, body: str, item_ids: list[int],
                      folder: str = "", tags: list[str] | tuple[str, ...] = ()) -> tuple[dict[str, Any], bool]:
        title = " ".join(str(title).split())
        body = str(body).strip()
        if not title:
            raise BrainError(422, "The title is empty.")
        if not body:
            raise BrainError(422, "The text is empty.")
        title, body, tag_tuple, folder = self._files._check(title, body, tags, folder)
        ids = sorted(set(item_ids))
        if len(ids) > MAX_ITEMS:
            raise BrainError(422, f"Name at most {MAX_ITEMS} items.")
        if ids:
            try:
                present = {item["id"] for item in (await self._stacks.view(uid, chat_id))["items"]}
            except StackError as error:
                raise BrainError(error.status, str(error)) from None
            if not set(ids) <= present:
                raise BrainError(422, "One of the named items is not in this chat's short-term memory.")
        fingerprint = hashlib.sha256(json.dumps([title, body, folder, list(tag_tuple)]).encode()).hexdigest()
        async with self._lock(uid):
            if uid in self._purged:
                raise BrainError(404, "No such account.")
            same = await self._store.query(PROPOSALS, {"owner": uid, "fingerprint": fingerprint}, limit=1)
            if same:
                existing = same[0]
                if existing["status"] == PENDING:
                    return view(existing), True
                if existing["status"] == DECLINED:
                    raise BrainError(409, "The user declined this suggestion. Do not propose it again.")
                raise BrainError(409, "The user already saved this suggestion. Do not propose it again.")
            if await self._store.query(PROPOSALS, {"owner": uid, "status": PENDING}, limit=1, offset=MAX_PENDING - 1):
                raise BrainError(409, f"You already have {MAX_PENDING} suggestions waiting. Ask the user to review them first.")
            doc = {"id": uuid.uuid4().hex, "owner": uid, "chat_id": chat_id, "item_ids": ids, "title": title, "body": body,
                   "folder": folder, "tags": list(tag_tuple), "fingerprint": fingerprint, "status": PENDING,
                   "created_at": _now(), "decided_at": None, "result_id": None}
            await self._store.put(PROPOSALS, doc["id"], doc)
            return view(doc), False

    async def pending(self, uid: str) -> list[dict[str, Any]]:
        docs = await self._store.query(PROPOSALS, {"owner": uid, "status": PENDING}, limit=MAX_PENDING)
        return [view(doc) for doc in sorted(docs, key=lambda doc: doc["created_at"], reverse=True)]

    async def _doc(self, uid: str, proposal_id: str) -> dict[str, Any]:
        doc = await self._store.get(PROPOSALS, proposal_id)
        if doc is None or doc["owner"] != uid:
            raise BrainError(404, _GONE)
        return doc

    async def get(self, uid: str, proposal_id: str) -> dict[str, Any]:
        return view(await self._doc(uid, proposal_id), detail=True)

    async def _pending_doc(self, uid: str, proposal_id: str) -> dict[str, Any]:
        doc = await self._doc(uid, proposal_id)
        if doc["status"] != PENDING:
            raise BrainError(409, "That suggestion is already decided.")
        return doc

    async def _close(self, doc: dict[str, Any], status: str, result_id: str | None = None) -> dict[str, Any]:
        doc["status"], doc["decided_at"], doc["result_id"], doc["body"] = status, _now(), result_id, ""
        await self._store.put(PROPOSALS, doc["id"], doc)
        return view(doc)

    async def accept(self, uid: str, proposal_id: str, title: str | None = None, folder: str | None = None,
                     remove_items: bool = False) -> dict[str, Any]:
        async with self._lock(uid):
            doc = await self._pending_doc(uid, proposal_id)
            record = await self._files.create(uid, title=doc["title"] if title is None else title, body=doc["body"], tags=doc["tags"],
                                              folder=doc["folder"] if folder is None else folder, actor="agent",
                                              record_id=uuid.UUID(hex=proposal_id))
            done = await self._close(doc, ACCEPTED, record.id)
            removed = 0
            for item_id in doc["item_ids"] if remove_items else ():
                try:
                    await self._stacks.remove(uid, doc["chat_id"], item_id)
                    removed += 1
                except StackError:
                    continue
                except DbGatewayError:
                    # Keep is already committed. Report only the removals confirmed by storage.
                    break
            return {**done, "removed": removed}

    async def decline(self, uid: str, proposal_id: str) -> dict[str, Any]:
        async with self._lock(uid):
            doc = await self._pending_doc(uid, proposal_id)
            try:
                await self._files.get(uid, proposal_id)
            except BrainError as error:
                if error.status != 404:
                    raise
                return await self._close(doc, DECLINED)
            # A previous Keep wrote the file before Treasury could record the decision.
            await self._close(doc, ACCEPTED, proposal_id)
            raise BrainError(409, "That suggestion is already decided.")

    async def purge(self, uid: str) -> None:
        async with self._lock(uid):
            self._purged.add(uid)
            while docs := await self._store.query(PROPOSALS, {"owner": uid}, limit=_PAGE):
                for doc in docs:
                    await self._store.delete(PROPOSALS, doc["id"])
