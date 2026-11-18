"""Armory's shared connection records and the legacy MCP adapter."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from src.citadel_auth import checked_address
from src.citadel_auth.policy import SERVICES

REQUIRED = {"bard": "Bard", "scribe": "Scribe", "reader": "Reader"}
_NAME = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
_HEADER = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_TOKEN = "X-Internal-Token"


def _base_record(name: str) -> dict:
    return {"name": name, "class": "required" if name in REQUIRED else "server",
            "label": REQUIRED.get(name, name), "enabled": True, "description": "",
            "web_url": None, "rest": None, "mcp": None}


def _http_url(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Enter an HTTP or HTTPS URL.")
    parts = urlsplit(value)
    base = f"{parts.scheme}://{parts.netloc}"
    checked_address(base)
    if "?" in value or "#" in value or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("Enter an HTTP or HTTPS URL without a query or fragment.")
    return base + parts.path


def _view_url(value: object) -> str | None:
    try:
        return _http_url(value)
    except ValueError:
        return None


def _origin(value: str | None) -> tuple[str, str | None, int] | None:
    if not value:
        return None
    try:
        url = urlsplit(value)
        return url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80)
    except ValueError:
        return None


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid connection text.")
    return value.strip()


def _credential(value: object) -> str:
    if (not isinstance(value, str) or len(value) > 4096
            or any(ord(c) < 32 or ord(c) > 126 for c in value)):
        raise ValueError("Invalid credential.")
    return value.strip()


def _auth(incoming: object, existing: dict) -> dict:
    if not isinstance(incoming, dict):
        raise ValueError("Invalid connection authentication.")
    kind = incoming.get("kind", existing.get("kind", "none"))
    if not isinstance(kind, str) or kind not in {"token", "headers", "internal", "none"}:
        raise ValueError("Unsupported connection authentication.")
    previous = existing if existing.get("kind") == kind else {}
    if kind == "token":
        token = incoming.get("token", previous.get("token"))
        return {"kind": kind, "token": _credential(token) if token is not None else None}
    if kind == "internal":
        audience = incoming.get("audience", previous.get("audience"))
        if not isinstance(audience, str) or audience not in SERVICES:
            raise ValueError("Choose a Citadel service for signed authentication.")
        return {"kind": kind, "audience": audience}
    if kind == "headers":
        headers = incoming.get("headers", previous.get("headers", {}))
        if not isinstance(headers, dict) or len(headers) > 20:
            raise ValueError("Invalid credential headers.")
        for name in headers:
            lower = name.lower()
            if (len(name) > 100 or not _HEADER.fullmatch(name) or lower.startswith(("x-requester-", "x-citadel-"))
                    or lower in {"host", "connection", "upgrade", "transfer-encoding", "content-length",
                                 "content-type", "content-encoding", "accept-encoding", "range", "x-filename"}):
                raise ValueError("Invalid credential header name.")
        return {"kind": kind, "headers": {name: _credential(value) for name, value in headers.items()}}
    return {"kind": "none"}


def auth_headers(auth: dict) -> dict[str, str]:
    if auth["kind"] == "token" and auth.get("token"):
        return {_TOKEN: auth["token"]}
    if auth["kind"] == "headers":
        return auth.get("headers", {}).copy()
    return {}


def ready_status(record: dict) -> dict:
    rest = record["rest"]
    label = REQUIRED.get(record["name"], record["label"])
    if not record["enabled"]:
        reason = f"{label} is disabled in Armory Admin."
    elif not rest:
        reason = f"Configure {label}'s REST connection in Armory Admin."
    elif record["class"] == "required" and not rest["auth"].get("token"):
        reason = f"Set the {label} token in Armory Admin."
    else:
        reason = None
    return {"ready": reason is None, "reason": reason}


def _legacy_mcp(entry: dict) -> dict:
    headers = entry.get("headers", {})
    if entry.get("internal"):
        auth = {"kind": "internal", "audience": entry.get("audience", "legion"), "legacy_headers": headers}
    elif isinstance(headers, dict) and len(headers) == 1 and next(iter(headers)).lower() == _TOKEN.lower():
        auth = {"kind": "token", "token": next(iter(headers.values()))}
    elif headers:
        auth = {"kind": "headers", "headers": headers}
    else:
        auth = {"kind": "none"}
    fields = {k: entry[k] for k in ("url", "command", "args", "forward_requester") if k in entry}
    return {**fields, "auth": auth, "legacy": True}


def extension_entry(record: dict):
    """Adapt one record to the existing ExtensionConfig loader."""
    mcp = record["mcp"]
    if "invalid_entry" in mcp:
        return mcp["invalid_entry"]
    result = {k: record[k] for k in ("label", "description", "web_url") if record[k] is not None}
    result.update({k: mcp[k] for k in ("url", "command", "args", "forward_requester") if k in mcp})
    auth = mcp["auth"]
    headers = auth_headers(auth)
    if auth["kind"] == "internal":
        result.update(internal=True, audience=auth["audience"])
        headers = auth.get("legacy_headers", {})
    if headers:
        result["headers"] = headers
    legacy_record = record.get("legacy_metadata", mcp.get("legacy"))
    escaped = result.copy() if mcp.get("legacy") else _escape_placeholders(result)
    if legacy_record:
        literal_fields = record.get("literal_metadata", ())
        for field in ("label", "description", "web_url"):
            if field in result:
                escaped[field] = _escape_placeholders(result[field]) if field in literal_fields else result[field]
    for field, flag in (("url", "legacy_url"), ("headers", "legacy_auth")):
        if mcp.get(flag) and field in result:
            escaped[field] = result[field]
    return escaped


def _escape_placeholders(value):
    if isinstance(value, str):
        return value.replace("$", "$$")
    if isinstance(value, dict):
        return {key: _escape_placeholders(item) for key, item in value.items()}
    return value


class ConnectionStore:
    """Keep migrations and partial updates atomic in the service settings database."""

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS connections (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            if (db.execute("SELECT 1 FROM sqlite_master WHERE name = 'extensions'").fetchone()
                    and db.execute("SELECT 1 FROM extensions LIMIT 1").fetchone()):
                db.execute("BEGIN IMMEDIATE")
                for name, data in db.execute("SELECT key, value FROM extensions").fetchall():
                    entry = json.loads(data)
                    record = _base_record(name)
                    if isinstance(entry, dict):
                        record.update(label=entry.get("label"), description=entry.get("description", ""),
                                      web_url=entry.get("web_url"), legacy_metadata=True)
                        record["mcp"] = _legacy_mcp(entry)
                    else:
                        record["mcp"] = {"invalid_entry": entry, "auth": {"kind": "none"}}
                    db.execute("INSERT OR IGNORE INTO connections VALUES (?, ?)", (name, json.dumps(record)))
                db.execute("DELETE FROM extensions")
                db.commit()
            yield db

    @staticmethod
    def _get(db, name: str) -> dict:
        row = db.execute("SELECT value FROM connections WHERE key = ?", (name,)).fetchone()
        return json.loads(row[0]) if row else _base_record(name)

    @staticmethod
    def _put(db, record: dict) -> None:
        db.execute("INSERT INTO connections VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (record["name"], json.dumps(record)))

    def get(self, name: str) -> dict:
        with self._open() as db:
            return self._get(db, name)

    def records(self) -> dict[str, dict]:
        records = {name: _base_record(name) for name in REQUIRED}
        with self._open() as db:
            records.update((name, json.loads(data)) for name, data in db.execute(
                "SELECT key, value FROM connections ORDER BY key"))
        return records

    def views(self) -> list[dict]:
        return [self.view(record) for record in self.records().values()]

    @staticmethod
    def view(record: dict) -> dict:
        view = {k: record[k] for k in ("name", "class", "label", "description", "enabled")}
        view["label"] = view["label"] or record["name"]
        view["web_url"] = _view_url(record["web_url"])
        for kind, field in (("mcp", "url"), ("rest", "base_url")):
            block = record[kind]
            view[kind] = None
            if block:
                auth = block["auth"]
                public_auth = {"kind": auth["kind"], "configured": bool(auth_headers(auth) or auth.get("audience"))}
                if auth["kind"] == "internal":
                    public_auth["audience"] = auth["audience"]
                view[kind] = {field: _view_url(block.get(field)), "auth": public_auth}
                if kind == "mcp":
                    view[kind]["forward_requester"] = bool(block.get("forward_requester"))
                    view[kind]["local"] = "command" in block
        return {**view, **ready_status(record)}

    def save_legacy_mcp(self, name: str, entry: dict, *, create: bool = False) -> str:
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            if create:
                base, number = name, 2
                while name in REQUIRED or db.execute("SELECT 1 FROM connections WHERE key = ?", (name,)).fetchone():
                    name = f"{base}_{number}"
                    number += 1
            record = self._get(db, name)
            record.update(label=entry["label"], description=entry["description"], web_url=entry.get("web_url"))
            record["literal_metadata"] = ["label", "description", "web_url"]
            record["mcp"] = _legacy_mcp(entry)
            self._put(db, record)
        return name

    def remove_legacy_mcp(self, name: str) -> None:
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self._get(db, name)
            if record["rest"] or name in REQUIRED:
                record["mcp"] = None
                self._put(db, record)
            else:
                db.execute("DELETE FROM connections WHERE key = ?", (name,))

    def update(self, name: str, changes: dict) -> dict:
        if (len(name) > 60 or not _NAME.fullmatch(name) or not isinstance(changes, dict)
                or changes.keys() - {"label", "description", "enabled", "web_url", "mcp", "rest"}):
            raise ValueError("Invalid connection name or fields.")
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            record = self._get(db, name)
            for field, limit in (("label", 120), ("description", 1000)):
                if field in changes:
                    record[field] = _text(changes[field], limit)
            if not record["label"]:
                raise ValueError("Enter a connection label.")
            if "enabled" in changes:
                if not isinstance(changes["enabled"], bool):
                    raise ValueError("Invalid enabled setting.")
                record["enabled"] = changes["enabled"]
            if "web_url" in changes:
                record["web_url"] = _http_url(changes["web_url"]) if changes["web_url"] else None
            literal_fields = set(record.get("literal_metadata", ())) | (changes.keys() & {"label", "description", "web_url"})
            if literal_fields:
                record["literal_metadata"] = sorted(literal_fields)
            for kind, field, validate in (("rest", "base_url", checked_address), ("mcp", "url", _http_url)):
                if kind not in changes:
                    continue
                incoming = changes[kind]
                if incoming is None:
                    record[kind] = None
                    continue
                if not isinstance(incoming, dict) or incoming.keys() - {field, "auth", "forward_requester"}:
                    raise ValueError("Invalid transport fields.")
                previous = record[kind] or {}
                record[kind] = self._transport(kind, field, validate, incoming, previous, name in REQUIRED)
            self._put(db, record)
        return record

    @staticmethod
    def _transport(kind, field, validate, incoming, previous, required) -> dict:
        legacy_url = (previous.get("legacy") or previous.get("legacy_url")) and (
            field not in incoming or incoming[field] == previous.get(field))
        address = previous.get(field) if legacy_url and previous.get(field) else validate(incoming.get(field, previous.get(field)))
        same_origin = _origin(address) == _origin(previous.get(field))
        previous_auth = previous.get("auth", {})
        if not same_origin:
            previous_auth = {key: value for key, value in previous_auth.items() if key in {"kind", "audience"}}
        incoming_auth = incoming.get("auth", {})
        auth = _auth(incoming_auth, previous_auth)
        retained_auth = (same_origin and auth["kind"] == previous_auth.get("kind")
                         and not ({"headers", "token", "audience"} & incoming_auth.keys()))
        if retained_auth and previous.get("legacy"):
            auth = previous["auth"]
        if required and kind == "rest" and auth["kind"] != "token":
            raise ValueError("Required REST connections use a tool-service token.")
        block = {field: address, "auth": auth}
        if kind == "mcp":
            if legacy_url:
                block["legacy_url"] = True
            if retained_auth and (previous.get("legacy") or previous.get("legacy_auth")):
                block["legacy_auth"] = True
            forward = incoming.get("forward_requester", previous.get("forward_requester", auth["kind"] == "token"))
            if not isinstance(forward, bool):
                raise ValueError("Invalid requester forwarding setting.")
            block["forward_requester"] = forward
        return block

    def remove(self, name: str) -> bool:
        if name in REQUIRED:
            raise ValueError("Required connections cannot be removed.")
        with self._open() as db:
            return bool(db.execute("DELETE FROM connections WHERE key = ?", (name,)).rowcount)
