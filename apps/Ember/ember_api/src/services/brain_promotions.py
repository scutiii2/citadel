"""Recoverable create-only Notes publication. Source Notes are never mutated."""
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db import utcnow
from src.services.brain_connections import BrainError, brain_path
from src.services.notes import NotesService, NoteNotFound

COLLECTION = "brain_promotions"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def note_hash(note) -> str:
    return text_hash(json.dumps({"title": note.title, "body": note.body, "tags": list(note.tags)},
                                sort_keys=True, ensure_ascii=False))


class PublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision: str = Field(max_length=64)
    scope: Literal["personal", "instance"]
    destination_revision: int = Field(ge=0)
    generation: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=500)
    draft: str = Field(min_length=1, max_length=40_000)
    idempotency_key: str = Field(min_length=1, max_length=100)
    shared_audience_reviewed: bool = False

    @field_validator("path")
    @classmethod
    def path_valid(cls, value):
        return brain_path(value)


class Promotions:
    def __init__(self, store, connections, remote, uid: str, *, publish: bool):
        self.store, self.connections, self.remote, self.uid = store, connections, remote, uid
        self.can_publish = publish

    async def list(self, note_id: str | None = None):
        rows = await self.store.query(COLLECTION, {"owner": self.uid}, limit=500)
        rows = [await self._current(row["id"]) for row in rows if row.get("owner") == self.uid]
        notes = {note.id: note_hash(note) for note in await NotesService(self.store, self.uid).list()}
        return [{k: v for k, v in row.items() if k not in {"draft", "owner", "idempotency_key"}} | {
            "source_changed": notes.get(row["note_id"]) != row["source_hash"]}
            for row in rows if row.get("owner") == self.uid and (note_id is None or row["note_id"] == note_id)]

    async def publish(self, note_id: str, body: PublicationInput):
        try:
            note = await NotesService(self.store, self.uid).get(note_id)
        except NoteNotFound:
            raise BrainError("Note not found", 404) from None
        if note_hash(note) != body.source_hash or note.updated_at != body.source_revision:
            raise BrainError("The Note changed. Review the current version before publishing.", 412)
        if body.scope == "instance" and not body.shared_audience_reviewed:
            raise BrainError("Review that all signed-in users can read this publication", 400)
        snapshot = await self.connections.resolve(body.scope, self.uid, write=True, publish=self.can_publish)
        if snapshot["revision"] != body.destination_revision or snapshot["generation"] != body.generation:
            raise BrainError("The destination changed. Review it again.", 412)
        key = text_hash("\0".join((self.uid, note.id, body.source_hash, snapshot["id"], snapshot["generation"])))
        request_key = text_hash(self.uid + "\0" + body.idempotency_key)
        claim = {"id": request_key, "owner": self.uid, "promotion_id": key}
        if not await self.store.create("brain_promotion_requests", request_key, claim):
            previous = await self.store.get("brain_promotion_requests", request_key)
            if previous.get("promotion_id") != key:
                raise BrainError("This idempotency key belongs to another publication")
        row = {"id": key, "owner": self.uid, "note_id": note.id, "source_hash": body.source_hash,
            "source_revision": body.source_revision, "connection_id": snapshot["id"], "scope": body.scope,
            "generation": snapshot["generation"], "destination_revision": snapshot["revision"],
            "path": body.path, "draft": body.draft, "published_hash": text_hash(body.draft),
            "idempotency_key": body.idempotency_key, "status": "pending", "attempt": 0, "created_at": utcnow().isoformat()}
        if not await self.store.create(COLLECTION, key, row):
            row = await self._current(key)
            if row["status"] == "conflict" and body.path != row["path"]:
                candidate = {**row, "attempt": row["attempt"] + 1, "path": body.path, "draft": body.draft,
                             "published_hash": text_hash(body.draft), "status": "pending"}
                # Only a confirmed, pre-dispatch collision permits a new path.
                # create() converges concurrent corrections on a single attempt.
                await self.store.create("brain_promotion_attempts", f"{key}:{candidate['attempt']}", candidate)
                row = await self._current(key)
            if row["status"] == "published":
                return self._receipt(row)
            if row["published_hash"] != text_hash(body.draft):
                raise BrainError("An earlier publication of this version is pending with a different draft. Reconcile it first.")
        # Reserve the draft/path durably before dispatch. Every retry and concurrent
        # submission uses the winning record, never another random destination.
        arguments = {"path": row["path"], "revision": row["destination_revision"], "generation": row["generation"]}
        try:
            existing = await self.remote.operation(self.uid, "read", body.scope, **arguments)
        except BrainError as error:
            if error.status != 404:
                raise
        else:
            if text_hash(existing.get("content", "")) != row["published_hash"]:
                if await self._decision(row, "conflict") == "conflict":
                    row = {**row, "status": "conflict"}
                    await self._save(row)
                raise BrainError("The reserved Obsidian path contains different content. It was not overwritten.")
            return await self._finish(row)
        if await self._decision(row, "write") != "write":
            raise BrainError("The reserved path conflicted. Review a different path before publishing.")
        try:
            await self.remote.operation(self.uid, "write", body.scope, text=row["draft"], **arguments)
        except BrainError as error:
            if error.status != 412:
                raise  # Unknown outcome stays pending; retry reads the reserved path.
            existing = await self.remote.operation(self.uid, "read", body.scope, **arguments)
            if text_hash(existing.get("content", "")) != row["published_hash"]:
                raise BrainError("A different document occupies the reserved path. Nothing was overwritten.") from None
        return await self._finish(row)

    async def _finish(self, row):
        row = {**row, "status": "published", "published_at": utcnow().isoformat()}
        await self._save(row)
        return self._receipt(row)

    async def _current(self, key):
        row = await self.store.get(COLLECTION, key)
        attempt = row.get("attempt", 0)
        if attempt:
            row = await self.store.get("brain_promotion_attempts", f"{key}:{attempt}") or row
        while following := await self.store.get("brain_promotion_attempts", f"{key}:{attempt + 1}"):
            row, attempt = following, attempt + 1
        decision = await self.store.get("brain_promotion_decisions", f"{key}:{attempt}")
        if decision and decision["decision"] == "conflict" and row["status"] != "published":
            row = {**row, "status": "conflict"}
        return row

    async def _decision(self, row, kind):
        key = f"{row['id']}:{row['attempt']}"
        await self.store.create("brain_promotion_decisions", key,
                                {"id": key, "owner": self.uid, "decision": kind})
        return (await self.store.get("brain_promotion_decisions", key))["decision"]

    async def _save(self, row):
        if row["attempt"]:
            await self.store.put("brain_promotion_attempts", f"{row['id']}:{row['attempt']}", row)
        await self.store.put(COLLECTION, row["id"], row)

    async def reconcile(self, key):
        root = await self.store.get(COLLECTION, key)
        if root is None or root.get("owner") != self.uid:
            raise BrainError("Publication not found", 404)
        row = await self._current(key)
        snapshot = await self.connections.resolve(row["scope"], self.uid, write=False, publish=self.can_publish)
        if snapshot["generation"] != row["generation"]:
            raise BrainError("The original destination was replaced; it cannot be reconciled through this connection.")
        try:
            found = await self.remote.operation(self.uid, "read", row["scope"], path=row["path"],
                revision=row["destination_revision"], generation=row["generation"])
        except BrainError as error:
            if error.status == 404:
                raise BrainError("No document is confirmed at the reserved path yet. The pending record is preserved.") from None
            raise
        if text_hash(found.get("content", "")) != row["published_hash"]:
            raise BrainError("Different content occupies the reserved path. It was not overwritten.")
        return await self._finish(row)

    @staticmethod
    def _receipt(row):
        return {k: v for k, v in row.items() if k not in {"owner", "draft", "idempotency_key"}}
