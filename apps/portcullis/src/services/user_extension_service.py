"""Private extensions: the MCP servers an account added for itself.

Stored as documents in db_gateway (collection "user_extensions", key "<owner uid>:<slug>", so
create-if-absent keeps an account's slugs unique). Header values are secrets: they are validated
here, encrypted with the SecretBox before they reach the gateway, and only this service decrypts
them. `ai_agent` validates again (it is the one that
connects), so the limits below are duplicated there on purpose.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from src.db import utcnow
from src.services.db_gateway import DocumentStore
from src.services.secret_box import SecretBox, SecretBoxError

COLLECTION = "user_extensions"
MAX_EXTENSIONS = 20
MAX_HEADERS = 20
MAX_VALUE = 2000
MAX_URL = 1000
MAX_LABEL = 60
MAX_DESCRIPTION = 300
MAX_SLUG = 40
SLUG_PATTERN = r"^[a-z0-9]+(_[a-z0-9]+)*$"
UNREADABLE_MESSAGE = "Its headers can't be read (the secrets key changed). Edit it to set them again."

_HEADER_NAME = re.compile(r"[A-Za-z0-9-]{1,64}")
_FORBIDDEN_HEADERS = frozenset(
    {"host", "content-length", "transfer-encoding", "connection", "upgrade", "te", "trailer", "proxy-authorization", "cookie"}
)
_NOT_SLUG = re.compile(r"[^a-z0-9]+")


class InvalidExtension(ValueError):
    """Input that cannot be saved. The message is safe to show the user."""


class ExtensionNotFound(Exception):
    """No such extension for this account."""


class ExtensionLimit(Exception):
    """The account already has MAX_EXTENSIONS extensions."""


def slugify(label: str) -> str:
    slug = _NOT_SLUG.sub("_", label.strip().lower()).strip("_")[:MAX_SLUG].strip("_")
    return slug or "extension"


def clean_label(label: str) -> str:
    cleaned = " ".join(label.split())
    if not cleaned:
        raise InvalidExtension("Enter a name")
    if len(cleaned) > MAX_LABEL:
        raise InvalidExtension(f"The name can be at most {MAX_LABEL} characters")
    return cleaned


def clean_description(description: str) -> str:
    cleaned = description.strip()
    if len(cleaned) > MAX_DESCRIPTION:
        raise InvalidExtension(f"The description can be at most {MAX_DESCRIPTION} characters")
    return cleaned


def clean_url(url: str) -> str:
    cleaned = url.strip()
    parts = urlsplit(cleaned)
    if not cleaned or len(cleaned) > MAX_URL or parts.scheme not in ("http", "https") or not parts.hostname:
        raise InvalidExtension("Enter an http or https address")
    if parts.username is not None or parts.password is not None:
        raise InvalidExtension("Put credentials in a header, not in the address")
    return cleaned


def clean_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    if len(headers) > MAX_HEADERS:
        raise InvalidExtension(f"At most {MAX_HEADERS} headers are allowed")
    cleaned: dict[str, str] = {}
    for name, value in headers.items():
        if not _HEADER_NAME.fullmatch(name):
            raise InvalidExtension("A header name may only use letters, digits and hyphens (64 at most)")
        if name.lower() in _FORBIDDEN_HEADERS:
            raise InvalidExtension(f"The header {name} can't be set")
        if not 1 <= len(value) <= MAX_VALUE:
            raise InvalidExtension(f"The value of {name} must be 1 to {MAX_VALUE} characters")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise InvalidExtension(f"The value of {name} has a control character")
        cleaned[name] = value
    return cleaned


@dataclass(frozen=True)
class ExtensionRecord:
    """One saved extension as the gateway holds it."""

    slug: str
    label: str
    description: str
    url: str
    headers_encrypted: str | None
    enabled: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> ExtensionRecord:
        return cls(
            doc["slug"], doc["label"], doc.get("description", ""), doc["url"], doc.get("headers_encrypted"),
            doc.get("enabled") is not False, doc["created_at"], doc["updated_at"],
        )

    def to_doc(self, owner_uid: str) -> dict[str, Any]:
        return {"owner": owner_uid, **asdict(self)}


@dataclass(frozen=True)
class StoredExtension:
    row: ExtensionRecord
    # None: the stored headers could not be decrypted (the key changed).
    headers: dict[str, str] | None

    @property
    def readable(self) -> bool:
        return self.headers is not None

    @property
    def header_names(self) -> list[str]:
        return sorted(self.headers or {})

    def __repr__(self) -> str:  # never show header values
        return f"StoredExtension(slug={self.row.slug!r}, readable={self.readable})"


@dataclass(frozen=True)
class TurnExtensions:
    # What ai_agent gets: {"id", "label", "url", "headers"}.
    items: tuple[dict[str, Any], ...]
    # Enabled extensions left out of the turn: {"id", "label", "error"}.
    skipped: tuple[dict[str, str], ...]


class UserExtensionService:
    def __init__(self, store: DocumentStore, owner_uid: str, box: SecretBox) -> None:
        self._store = store
        self._owner = owner_uid
        self._box = box

    def _key(self, slug: str) -> str:
        return f"{self._owner}:{slug}"

    def _stored(self, row: ExtensionRecord) -> StoredExtension:
        if row.headers_encrypted is None:
            return StoredExtension(row, {})
        try:
            return StoredExtension(row, self._box.decrypt_map(row.headers_encrypted))
        except SecretBoxError:
            return StoredExtension(row, None)

    async def _rows(self) -> list[ExtensionRecord]:
        docs = await self._store.query(COLLECTION, {"owner": self._owner}, limit=MAX_EXTENSIONS + 1)
        return sorted((ExtensionRecord.from_doc(d) for d in docs), key=lambda r: (r.created_at, r.slug))

    async def _row(self, slug: str) -> ExtensionRecord:
        doc = await self._store.get(COLLECTION, self._key(slug))
        if doc is None or doc.get("owner") != self._owner:
            raise ExtensionNotFound(slug)
        return ExtensionRecord.from_doc(doc)

    async def list(self) -> list[StoredExtension]:
        return [self._stored(row) for row in await self._rows()]

    async def get(self, slug: str) -> StoredExtension:
        return self._stored(await self._row(slug))

    async def create(
        self, *, label: str, url: str, description: str = "", headers: Mapping[str, str] | None = None
    ) -> StoredExtension:
        label = clean_label(label)
        url = clean_url(url)
        description = clean_description(description)
        values = clean_headers(headers)
        rows = await self._rows()
        if len(rows) >= MAX_EXTENSIONS:
            raise ExtensionLimit
        taken = {row.slug for row in rows}
        base = slugify(label)
        slug, number = base, 2
        now = utcnow().isoformat()
        while True:
            while slug in taken:
                suffix = f"_{number}"
                slug = f"{base[: MAX_SLUG - len(suffix)].rstrip('_')}{suffix}"
                number += 1
            row = ExtensionRecord(
                slug, label, description, url, self._box.encrypt_map(values) if values else None, True, now, now
            )
            # Create-if-absent: a slug taken by a racing request is skipped, not overwritten.
            if await self._store.create(COLLECTION, self._key(slug), row.to_doc(self._owner)):
                return StoredExtension(row, values)
            taken.add(slug)

    async def update(
        self,
        slug: str,
        *,
        label: str | None = None,
        description: str | None = None,
        url: str | None = None,
        headers: Mapping[str, str] | None = None,
        enabled: bool | None = None,
    ) -> StoredExtension:
        """`headers`, when given (even empty), replaces the whole set. A new host
        without new headers clears the saved ones: a token is never silently
        sent to another host."""
        row = await self._row(slug)
        changes: dict[str, Any] = {}
        if label is not None:
            changes["label"] = clean_label(label)
        if description is not None:
            changes["description"] = clean_description(description)
        host_changed = False
        if url is not None:
            new_url = clean_url(url)
            host_changed = urlsplit(new_url).hostname != urlsplit(row.url).hostname
            changes["url"] = new_url
        if headers is not None:
            values = clean_headers(headers)
            changes["headers_encrypted"] = self._box.encrypt_map(values) if values else None
        elif host_changed:
            changes["headers_encrypted"] = None
        if enabled is not None:
            changes["enabled"] = enabled
        row = replace(row, updated_at=utcnow().isoformat(), **changes)
        await self._store.put(COLLECTION, self._key(slug), row.to_doc(self._owner))
        return self._stored(row)

    async def delete(self, slug: str) -> None:
        await self._row(slug)
        await self._store.delete(COLLECTION, self._key(slug))

    async def enabled_for_turn(self) -> TurnExtensions:
        items: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for row in await self._rows():
            if not row.enabled:
                continue
            stored = self._stored(row)
            if stored.headers is None:
                skipped.append({"id": row.slug, "label": row.label, "error": UNREADABLE_MESSAGE})
            else:
                items.append({"id": row.slug, "label": row.label, "url": row.url, "headers": dict(stored.headers)})
        return TurnExtensions(tuple(items), tuple(skipped))


async def purge_owner(store: DocumentStore, owner_uid: str) -> int:
    """Delete every extension of one account (used when the account is deleted). Returns the count."""
    removed = 0
    for _ in range(20):
        docs = await store.query(COLLECTION, {"owner": owner_uid}, limit=MAX_EXTENSIONS + 1)
        if not docs:
            break
        for doc in docs:
            removed += await store.delete(COLLECTION, f"{owner_uid}:{doc['slug']}")
    return removed
