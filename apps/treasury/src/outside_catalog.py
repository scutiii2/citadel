# apps/treasury/src/outside_catalog.py
"""Outside services: where the tool services and gateways Citadel calls are. Addresses only, never tokens.

Three tables in `.data/treasury/settings.db`: `outside_groups` (service id -> name), `outside_origins`
(origin id -> service id and origin) and `outside_users` (which Citadel service uses which group).
The name is a label; consumers store the ids, so a rename breaks nothing.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from src.citadel_auth import checked_address, settings_store

GROUPS_TABLE = "outside_groups"
ORIGINS_TABLE = "outside_origins"
USERS_TABLE = "outside_users"
RESERVED = frozenset({"portcullis", "stronghold", "armory", "legion", "treasury"})
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_DEFAULT_PORT = {"http": 80, "https": 443}
_DNS_HOST = re.compile(rb"[a-z0-9._-]+", re.IGNORECASE)


class OutsideCatalogError(ValueError):
    """A rejected change; the message is safe to show."""


class NotFound(OutsideCatalogError):
    pass


class InUse(OutsideCatalogError):
    def __init__(self, users: list[str]) -> None:
        super().__init__("in use by " + ", ".join(users))
        self.users = users


def split_origin(value: object) -> tuple[str, str]:
    """`(origin, path)` of an address. The origin is `scheme://host[:port]` with default ports dropped."""
    text = value.strip() if isinstance(value, str) else ""
    try:
        parts = urlsplit(text)
        port = parts.port  # raises on a malformed port
        hostname = parts.hostname
        if (parts.scheme not in _DEFAULT_PORT or not hostname
                or parts.username is not None or parts.password is not None
                or "?" in text or "#" in text or "\\" in text or port == 0 or parts.netloc.endswith(":")
                or any(char.isspace() or ord(char) < 32 for char in text)):
            raise ValueError
        if ":" not in hostname and not _DNS_HOST.fullmatch(hostname.encode("idna")):
            raise ValueError
        checked_address(f"{parts.scheme}://{parts.netloc}")
    except ValueError:
        raise OutsideCatalogError("an address looks like http://host:port, optionally followed by a path") from None
    host = f"[{hostname}]" if ":" in hostname else hostname
    shown = f":{port}" if port not in (None, _DEFAULT_PORT[parts.scheme]) else ""
    return f"{parts.scheme}://{host}{shown}", parts.path.rstrip("/")


def _clean_name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise OutsideCatalogError("this address is new: give it a name")
    text = name.strip().lower()
    if not _NAME.fullmatch(text):
        raise OutsideCatalogError("a name uses lowercase letters, digits and hyphens, up to 40 characters")
    if text in RESERVED:
        raise OutsideCatalogError(f"{text!r} is the name of a Citadel service")
    return text


@contextmanager
def _transaction(db: Path, *, write: bool = False):
    """Use the settings-store table format with one snapshot or atomic mutation."""
    with closing(settings_store._connect(db, GROUPS_TABLE)) as connection, connection:
        for table in (ORIGINS_TABLE, USERS_TABLE):
            connection.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield connection


def _state(connection: sqlite3.Connection) -> tuple[dict, dict, dict]:
    def read(table: str) -> dict:
        return {key: json.loads(value) for key, value in connection.execute(f"SELECT key, value FROM {table}")}

    return read(GROUPS_TABLE), read(ORIGINS_TABLE), read(USERS_TABLE)


def _put(connection: sqlite3.Connection, table: str, key: str, value: dict) -> None:
    connection.execute(
        f"INSERT INTO {table} (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def _delete(connection: sqlite3.Connection, table: str, key: str) -> None:
    connection.execute(f"DELETE FROM {table} WHERE key = ?", (key,))


def _row(service_id: str, groups: dict, origins: dict, users: dict) -> dict:
    mine = sorted((o["origin"], oid) for oid, o in origins.items() if o["service_id"] == service_id)
    return {
        "service_id": service_id,
        "name": groups[service_id]["name"],
        "origins": [{"origin_id": oid, "origin": origin} for origin, oid in mine],
        "used_by": _users_of(users, service_id),
    }


def view(db: Path) -> dict:
    with _transaction(db) as connection:
        groups, origins, users = _state(connection)
    ordered = sorted(groups, key=lambda sid: groups[sid]["name"])
    return {"groups": [_row(sid, groups, origins, users) for sid in ordered]}


def add_origin(db: Path, origin: object, name: object, consumer: str) -> dict:
    """Find the origin and return its group (the name is then ignored), or create it under `name`:
    a new name makes a group, an existing name adds the origin to that group. Records the consumer."""
    clean, _ = split_origin(origin)
    with _transaction(db, write=True) as connection:
        groups, origins, users = _state(connection)
        found = next((o for o in origins.values() if o["origin"] == clean), None)
        if found is not None:
            service_id = found["service_id"]
        else:
            label = _clean_name(name)
            service_id = next((sid for sid, g in groups.items() if g["name"] == label), None)
            if service_id is None:
                service_id = uuid.uuid4().hex
                groups[service_id] = {"name": label}
                _put(connection, GROUPS_TABLE, service_id, groups[service_id])
            origin_id = uuid.uuid4().hex
            origins[origin_id] = {"service_id": service_id, "origin": clean}
            _put(connection, ORIGINS_TABLE, origin_id, origins[origin_id])
        user_key = f"{service_id}:{consumer}"
        users[user_key] = {"service_id": service_id, "consumer": consumer}
        _put(connection, USERS_TABLE, user_key, users[user_key])
        return _row(service_id, groups, origins, users)


def rename_group(db: Path, service_id: str, name: object) -> dict:
    label = _clean_name(name)
    with _transaction(db, write=True) as connection:
        groups, origins, users = _state(connection)
        if service_id not in groups:
            raise NotFound("no such service")
        if any(sid != service_id and g["name"] == label for sid, g in groups.items()):
            raise OutsideCatalogError(f"the name {label!r} is already used")
        groups[service_id] = {"name": label}
        _put(connection, GROUPS_TABLE, service_id, groups[service_id])
        return _row(service_id, groups, origins, users)


def _users_of(users: dict, service_id: str) -> list[str]:
    return sorted(u["consumer"] for u in users.values() if u["service_id"] == service_id)


def delete_origin(db: Path, origin_id: str, confirm: bool = False) -> None:
    with _transaction(db, write=True) as connection:
        _groups, origins, users = _state(connection)
        if origin_id not in origins:
            raise NotFound("no such origin")
        used = _users_of(users, origins[origin_id]["service_id"])
        if used and not confirm:
            raise InUse(used)
        _delete(connection, ORIGINS_TABLE, origin_id)


def delete_group(db: Path, service_id: str, confirm: bool = False) -> None:
    with _transaction(db, write=True) as connection:
        groups, origins, users = _state(connection)
        if service_id not in groups:
            raise NotFound("no such service")
        used = _users_of(users, service_id)
        if used and not confirm:
            raise InUse(used)
        for oid, o in origins.items():
            if o["service_id"] == service_id:
                _delete(connection, ORIGINS_TABLE, oid)
        for key, u in users.items():
            if u["service_id"] == service_id:
                _delete(connection, USERS_TABLE, key)
        _delete(connection, GROUPS_TABLE, service_id)


def lookup(db: Path, address: object) -> dict:
    """Is this address's origin in the catalog? Read only: nothing is recorded."""
    origin, path = split_origin(address)
    with _transaction(db) as connection:
        groups, origins, users = _state(connection)
    for origin_id, row in origins.items():
        if row["origin"] == origin:
            return {"found": True, "origin": origin, "path": path, "origin_id": origin_id,
                    "group": _row(row["service_id"], groups, origins, users)}
    return {"found": False, "origin": origin, "path": path, "origin_id": None, "group": None}
