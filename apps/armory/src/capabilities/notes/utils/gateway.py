"""Reads and writes ember's notes in db_gateway (one instance and connection, over HTTP).

ember_api owns the notes and its Notes page; this is the agents' side door. The record shape
is ember_api's (`apps/Ember/ember_api/src/services/notes.py`): collection "notes", key a
32-hex id, fields id, owner, title, body, tags, agent_readable, created_at, updated_at. A note
an agent wrote also carries `last_editor: "agent"`, which ember_api keeps as it is.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

COLLECTION = "notes"
MAX_NOTES = 200  # ember_api's per-account cap
_NO_RECORD = "no record"


class NotesGatewayError(Exception):
    """db_gateway could not be reached or refused the call."""


class NotesGateway:
    def __init__(self, base_url: str, instance: str, connection: str, token: str, timeout: float = 5.0) -> None:
        self._base = (
            base_url.rstrip("/")
            + f"/instances/{quote(instance, safe='')}/connections/{quote(connection, safe='')}"
            + f"/collections/{COLLECTION}"
        )
        self._token = token
        self._timeout = timeout

    def get(self, key: str) -> dict[str, Any] | None:
        """One note document, or None when there is no such record."""
        try:
            return self._send("GET", f"/records/{quote(key, safe='')}")["doc"]
        except _Missing:
            return None

    def put(self, key: str, doc: dict[str, Any]) -> None:
        """Store (replace) one note document."""
        self._send("PUT", f"/records/{quote(key, safe='')}", {"doc": doc})

    def count_owned(self, owner: str) -> int:
        """How many notes `owner` has, shared with agents or not (ember_api caps it at MAX_NOTES)."""
        body = {"filters": {"owner": owner}, "limit": MAX_NOTES, "offset": 0}
        return len(self._send("POST", "/query", body)["docs"])

    def readable_by_agents(self, owner: str) -> list[dict[str, Any]]:
        """Every note of `owner` that the owner let agents read, newest edit first."""
        body = {"filters": {"owner": owner, "agent_readable": True}, "limit": MAX_NOTES, "offset": 0}
        docs = self._send("POST", "/query", body)["docs"]
        return sorted(docs, key=lambda doc: str(doc.get("updated_at", "")), reverse=True)

    def _send(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["X-Internal-Token"] = self._token
        request = urllib.request.Request(
            self._base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310 - base URL comes from config, not a caller
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 404 and _error_text(error).startswith(_NO_RECORD):
                raise _Missing from error
            raise NotesGatewayError(f"db_gateway answered HTTP {error.code}: {_error_text(error)}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise NotesGatewayError(f"Could not reach db_gateway: {error}") from error


class _Missing(Exception):
    pass


def _error_text(error: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(error.read()).get("error", ""))
    except (ValueError, AttributeError):
        return ""
