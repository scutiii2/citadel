"""Reads and writes ember's notes in db_gateway over HTTP.
Record shape is portcullis's (`apps/portcullis/src/services/notes.py`); agent-written notes carry `last_editor: "agent"`."""

from __future__ import annotations

import json
import asyncio
import httpx
from src.citadel_auth import service_client
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

COLLECTION = "notes"
MAX_NOTES = 200  # portcullis's per-account cap
_NO_RECORD = "no record"


class NotesGatewayError(Exception):
    """db_gateway could not be reached or refused the call."""


class NotesGateway:
    def __init__(self, base_url: str, instance: str, connection: str, keyring, timeout: float = 5.0) -> None:
        self._base = (
            base_url.rstrip("/")
            + f"/instances/{quote(instance, safe='')}/connections/{quote(connection, safe='')}"
            + f"/collections/{COLLECTION}"
        )
        self._keyring = keyring
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
        """How many notes `owner` has, shared with agents or not (portcullis caps it at MAX_NOTES)."""
        body = {"filters": {"owner": owner}, "limit": MAX_NOTES, "offset": 0}
        return len(self._send("POST", "/query", body)["docs"])

    def readable_by_agents(self, owner: str) -> list[dict[str, Any]]:
        """Every note of `owner` that the owner let agents read, newest edit first."""
        body = {"filters": {"owner": owner, "agent_readable": True}, "limit": MAX_NOTES, "offset": 0}
        docs = self._send("POST", "/query", body)["docs"]
        return sorted(docs, key=lambda doc: str(doc.get("updated_at", "")), reverse=True)

    def _send(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        """Bridge existing offloaded synchronous note operations to async HTTP."""
        return asyncio.run(self._send_async(method, path, body))

    async def _send_async(self, method: str, path: str, body: dict | None) -> dict[str, Any]:
        try:
            async with service_client(self._keyring, "treasury", timeout=self._timeout) as client:
                response = await client.request(method, self._base + path, json=body)
            payload = response.json()
            if response.status_code == 404 and str(payload.get("error", "")).startswith(_NO_RECORD):
                raise _Missing
            if response.is_error:
                raise NotesGatewayError(f"db_gateway answered HTTP {response.status_code}: {payload.get('error', '')}")
            return payload
        except (httpx.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            raise NotesGatewayError(f"Could not reach db_gateway: {error}") from error


class _Missing(Exception):
    pass


def _error_text(error: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(error.read()).get("error", ""))
    except (ValueError, AttributeError):
        return ""
