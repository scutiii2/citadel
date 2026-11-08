"""Encrypted brain connections. Immutable revisions make concurrent saves atomic.

The head document is only a hint: readers follow subsequent committed revisions,
so a delayed or failed hint write cannot hide a successfully saved revision.
"""
from __future__ import annotations

import hashlib
import uuid
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db import utcnow
from src.services.db_gateway import DocumentStore, DbGatewayError
from src.services.secret_box import SecretBox, SecretBoxError

COLLECTION = "brain_connections"
REVISIONS = "brain_connection_revisions"
PUBLISH = "brain.instance.publish"
SCOPES = {"instance", "personal"}


class BrainError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def brain_path(value: str, *, folder: bool = False) -> str:
    path = value.rstrip("/") if folder else value
    if (not folder and not path.lower().endswith(".md")) or path.startswith("/") or any(
        c in path for c in "\\:%"
    ) or any(ord(c) < 32 or ord(c) == 127 for c in path) or (
        path and any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("Use a vault-relative path without absolute or encoded segments")
    return path


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    label: str = Field(min_length=1, max_length=80)
    endpoint: str = Field(min_length=1, max_length=1000)
    api_key: str | None = Field(default=None, max_length=4096, repr=False, exclude=True)
    enabled: bool = True
    allow_write: bool = False
    folder: str = Field(default="Inbox", max_length=240)
    expected_revision: int = Field(default=0, ge=0)

    @field_validator("endpoint")
    @classmethod
    def endpoint_valid(cls, value):
        try:
            parts = urlsplit(value)
            if (parts.scheme != "https" or not parts.hostname or parts.port == 0 or parts.username
                or parts.password or parts.query or parts.fragment or any(c.isspace() for c in value)):
                raise ValueError()
        except ValueError:
            raise ValueError("Use an HTTPS endpoint without credentials, query or fragment") from None
        return value.rstrip("/")

    @field_validator("folder")
    @classmethod
    def folder_valid(cls, value):
        return brain_path(value, folder=True)

    @field_validator("api_key")
    @classmethod
    def key_valid(cls, value):
        if value is not None and (not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("Enter a valid API key, or leave it unchanged")
        return value


class BrainConnections:
    def __init__(self, store: DocumentStore, box: SecretBox):
        self.store, self.box = store, box

    @staticmethod
    def connection_id(scope: str, uid: str) -> str:
        if scope not in SCOPES or not uid and scope == "personal":
            raise BrainError("A valid brain destination and signed-in owner are required", 403)
        return "instance" if scope == "instance" else "personal-" + hashlib.sha256(uid.encode()).hexdigest()[:32]

    async def current(self, scope: str, uid: str) -> dict | None:
        key = self.connection_id(scope, uid)
        row = await self.store.get(COLLECTION, key)
        revision = int(row["revision"]) if row else 0
        while True:
            following = await self.store.get(REVISIONS, f"{key}:{revision + 1}")
            if following is None:
                break
            row, revision = following, revision + 1
        if row and (row.get("id") != key or row.get("owner") != (uid if scope == "personal" else "")):
            raise BrainError("Brain connection is unavailable", 503)
        return row

    @staticmethod
    def public(row: dict | None, scope: str) -> dict:
        if row is None:
            return {"id": "instance" if scope == "instance" else None, "scope": scope,
                "label": "Instance Brain" if scope == "instance" else "Personal Brain",
                "endpoint": "", "folder": "Inbox", "enabled": scope == "instance",
                "allow_write": False, "credential_configured": False,
                "revision": 0, "generation": "legacy" if scope == "instance" else None,
                "status": "legacy" if scope == "instance" else "not_configured"}
        return {**{key: row[key] for key in ("id", "scope", "label", "endpoint", "folder", "enabled",
                "allow_write", "revision", "generation", "updated_at")},
                "credential_configured": bool(row.get("credential")),
                "status": "configured" if row["enabled"] else "disabled"}

    async def get(self, scope: str, uid: str) -> dict:
        return self.public(await self.current(scope, uid), scope)

    async def candidate(self, scope: str, uid: str, value: ConnectionInput) -> dict:
        previous = await self.current(scope, uid)
        if (previous["revision"] if previous else 0) != value.expected_revision:
            raise BrainError("The connection changed. Reload before saving.")
        credential = self.box.encrypt_map({"api_key": value.api_key}) if value.api_key is not None else (
            previous.get("credential") if previous else None)
        if value.enabled and not credential:
            raise BrainError("Enter the Obsidian API key before enabling the connection", 400)
        return {**value.model_dump(exclude={"expected_revision"}),
            "id": self.connection_id(scope, uid), "scope": scope, "owner": uid if scope == "personal" else "",
            "credential": credential, "revision": value.expected_revision + 1,
            "generation": uuid.uuid4().hex, "updated_at": utcnow().isoformat()}

    async def save(self, scope: str, uid: str, value: ConnectionInput) -> dict:
        row = await self.candidate(scope, uid, value)
        if not await self.store.create(REVISIONS, f"{row['id']}:{row['revision']}", row):
            raise BrainError("The connection changed. Reload before saving.")
        try:
            await self.store.put(COLLECTION, row["id"], row)
        except DbGatewayError:
            pass  # The committed revision remains discoverable from its predecessor.
        return self.public(row, scope)

    def snapshot(self, row: dict) -> dict:
        try:
            key = self.box.decrypt_map(row["credential"])["api_key"]
        except (SecretBoxError, KeyError, TypeError):
            raise BrainError("The brain credential cannot be read. Enter it again.", 503) from None
        return {**self.public(row, row["scope"]), "api_key": key, "source": "remote", "verify_tls": True}

    async def resolve(self, scope: str, uid: str, *, write: bool, publish: bool) -> dict:
        if not uid:
            raise BrainError("A signed-in user is required", 403)
        if write and scope == "instance" and not publish:
            raise BrainError("Missing permission: brain.instance.publish", 403)
        row = await self.current(scope, uid)
        if row is None and scope == "instance":
            return {"id": "instance", "scope": "instance", "revision": 0, "generation": "legacy",
                "label": "Instance Brain", "folder": "Inbox", "source": "legacy"}
        if row is None:
            raise BrainError("Personal Brain is not configured", 404)
        if not row["enabled"]:
            raise BrainError("This brain connection is disabled")
        if write and not row["allow_write"]:
            raise BrainError("Writes to this brain are disabled", 403)
        return self.snapshot(row)


async def purge_owner(store: DocumentStore, uid: str) -> None:
    for collection in (COLLECTION, REVISIONS, "brain_promotions", "brain_suggestions", "brain_promotion_requests", "brain_promotion_attempts", "brain_promotion_decisions"):
        while docs := await store.query(collection, {"owner": uid}, limit=500):
            for row in docs:
                key = f"{row['id']}:{row['revision']}" if collection == REVISIONS else (
                    f"{row['id']}:{row['attempt']}" if collection == "brain_promotion_attempts" else row["id"])
                await store.delete(collection, key)
