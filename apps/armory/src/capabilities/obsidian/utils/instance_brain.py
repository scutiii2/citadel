"""Armory's encrypted Instance Brain, with a durable migration marker and revision CAS."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError, vault_path

LEGACY = {"label": "Instance Brain", "endpoint": "", "folder": "Inbox", "enabled": True,
          "allow_write": False, "revision": 0, "generation": "legacy", "updated_at": None}


class DisableInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_revision: int = Field(default=0, ge=0)


class ConnectionInput(DisableInput):
    label: str = Field(min_length=1, max_length=80)
    endpoint: str = Field(min_length=1, max_length=1000)
    api_key: str | None = Field(default=None, max_length=4096, repr=False, exclude=True)
    enabled: bool = True
    allow_write: bool = False
    folder: str = Field(default="Inbox", max_length=240)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            if (parts.scheme == "https" and parts.hostname and parts.port != 0
                    and parts.username is None and parts.password is None and "?" not in value
                    and "#" not in value and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)):
                return value.rstrip("/")
        except ValueError:
            pass
        raise ValueError("Use an HTTPS endpoint without credentials, query or fragment")

    @field_validator("folder")
    @classmethod
    def validate_folder(cls, value: str) -> str:
        try:
            return vault_path(value.rstrip("/"), folder=True)
        except ObsidianGatewayError as error:
            raise ValueError(str(error)) from None

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("Enter a valid API key, or leave it unchanged")
        return value


class ImportedConnection(ConnectionInput):
    revision: int = Field(gt=0)
    generation: str = Field(min_length=1, max_length=100)
    updated_at: datetime


def _origin(endpoint: str):
    parsed = urlsplit(endpoint)
    return parsed.hostname, parsed.port or 443


def _has_saved_credential(database: Path) -> bool:
    if not database.is_file():
        return False
    with closing(sqlite3.connect(database, timeout=10)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'instance_brain'").fetchone():
            return False
        entry = db.execute("SELECT record FROM instance_brain WHERE id = 1").fetchone()
        return bool(entry and (json.loads(entry[0]) or {}).get("credential"))


def load_box(directory: Path, database: Path) -> Fernet:
    """Use separate persistent encryption material so service-signing rotation is independent."""
    path = directory / "brain-storage.key"
    if not path.exists():
        if _has_saved_credential(database):
            raise OSError("Restore the Armory identity backup to read the Instance Brain credential.")
        temporary = directory / f"brain-storage.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(Fernet.generate_key())
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    if os.name == "posix":
        # The database can be on a different volume. Persist the key's directory entry before acknowledging import.
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return Fernet(path.read_bytes())


class InstanceBrainStore:
    def __init__(self, path: Path, box: Fernet | None):
        self.path, self._box = path, box

    @contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS instance_brain (id INTEGER PRIMARY KEY, record TEXT, retirement TEXT)")
            yield db

    @staticmethod
    def _read(db):
        entry = db.execute("SELECT record FROM instance_brain WHERE id = 1").fetchone()
        if entry is None:
            raise ObsidianGatewayError("Instance Brain migration is pending. Try again shortly.", status=503)
        return json.loads(entry[0])

    @staticmethod
    def _view(row):
        values = LEGACY if row is None else row
        status = "legacy" if row is None else "configured" if row["enabled"] else "disabled"
        return {**{name: values[name] for name in LEGACY}, "id": "instance", "scope": "instance",
                "status": status, "credential_configured": bool(values.get("credential"))}

    def migration(self) -> tuple[bool, list | None]:
        with self._db() as db:
            entry = db.execute("SELECT record, retirement FROM instance_brain WHERE id = 1").fetchone()
        if entry is None:
            return False, None
        pending = json.loads(entry[1])
        if pending:
            row = json.loads(entry[0])
            if row.get("credential"):
                self._credential(row)  # Never acknowledge credentials this installation cannot read.
        return True, pending

    def import_once(self, previous):
        record = retirement = None
        if previous is not None:
            old = ImportedConnection.model_validate(previous)
            if old.enabled and not old.api_key:
                raise ValueError("a managed connection requires a credential")
            record = old.model_dump(mode="json", exclude={"expected_revision"})
            record["credential"] = self._encrypt(old.api_key) if old.api_key else None
            retirement = [old.revision, old.generation]
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO instance_brain VALUES (1, ?, ?)",
                       (json.dumps(record), json.dumps(retirement)))

    def migrated(self):
        with self._db() as db:
            db.execute("UPDATE instance_brain SET retirement = 'null' WHERE id = 1")

    def view(self):
        with self._db() as db:
            return self._view(self._read(db))

    def _encryption_box(self) -> Fernet:
        if self._box is None:
            raise ObsidianGatewayError("Instance Brain encryption is unavailable. Restore the Armory identity backup.",
                                       status=503)
        return self._box

    def _encrypt(self, value: str) -> str:
        return self._encryption_box().encrypt(value.encode()).decode()

    def _credential(self, row: dict) -> str:
        try:
            return self._encryption_box().decrypt(row["credential"].encode()).decode()
        except (InvalidToken, UnicodeError, KeyError, AttributeError):
            raise ObsidianGatewayError("The brain credential cannot be read. Enter it again.", status=503) from None

    def _snapshot(self, row: dict | None) -> dict:
        if row is None:
            return {**self._view(None), "source": "legacy"}
        return {**self._view(row), "api_key": self._credential(row), "source": "remote"}

    def destination(self, *, legacy_writable: bool):
        with self._db() as db:
            row = self._read(db)
        view = self._view(row)
        writable = row is None and legacy_writable
        if row is not None and row["enabled"] and row["allow_write"]:
            try:
                writable = bool(self._credential(row))
            except ObsidianGatewayError:
                pass
        return {**{k: view[k] for k in ("id", "scope", "label", "folder", "enabled", "revision", "generation", "status")},
                "writable": writable}

    def snapshot(self, *, write=False):
        with self._db() as db:
            row = self._read(db)
        if row is not None:
            if not row["enabled"]:
                raise ObsidianGatewayError("This brain connection is disabled", status=409)
            if write and not row["allow_write"]:
                raise ObsidianGatewayError("Writes to this brain are disabled", status=403)
        return self._snapshot(row)

    def _candidate(self, previous, value: ConnectionInput):
        self._check_revision(previous, value.expected_revision)
        credential = previous.get("credential") if previous else None
        if value.api_key is not None:
            credential = self._encrypt(value.api_key)
        elif credential and _origin(value.endpoint) != _origin(previous["endpoint"]):
            raise ObsidianGatewayError("Enter an API key when changing the vault origin", status=400)
        if value.enabled and not credential:
            raise ObsidianGatewayError("Enter the Obsidian API key before enabling the connection", status=400)
        return {**value.model_dump(exclude={"expected_revision"}), "credential": credential,
                "revision": value.expected_revision + 1, "generation": uuid.uuid4().hex,
                "updated_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def _check_revision(previous, expected):
        if (previous or LEGACY)["revision"] != expected:
            raise ObsidianGatewayError("The connection changed. Reload before saving.", status=409)

    def candidate(self, value: ConnectionInput):
        with self._db() as db:
            return self._snapshot(self._candidate(self._read(db), value))

    def save(self, value: ConnectionInput):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._read(db)
            row = self._candidate(previous, value)
            db.execute("UPDATE instance_brain SET record = ? WHERE id = 1", (json.dumps(row),))
        return self._view(row), (previous or LEGACY)["generation"]

    def disable(self, expected_revision: int):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._read(db)
            self._check_revision(previous, expected_revision)
            row = {**(previous or LEGACY), "enabled": False, "revision": expected_revision + 1,
                   "generation": uuid.uuid4().hex, "updated_at": datetime.now(timezone.utc).isoformat()}
            db.execute("UPDATE instance_brain SET record = ? WHERE id = 1", (json.dumps(row),))
        return self._view(row), (previous or LEGACY)["generation"]
