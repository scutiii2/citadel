"""Typed read-only operations on the notes a user let agents read.

ember_api owns and writes the notes; db_gateway stores them. This reads them for the
asking account only (`identity_context.current_uid()` is ember's account uid, the same
value ember_api stores as a note's owner) and only the notes whose `agent_readable`
switch is on. Anything else, including another account's note and a note whose switch is
off, is reported as "no such note" so a caller cannot tell the difference.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.capabilities.notes.contract import (
    NoteHit,
    NoteListResult,
    NoteResult,
    NoteSearchResult,
    NoteSummary,
)
from src.capabilities.notes.utils.gateway import NotesGateway, NotesGatewayError
from src.config import settings
from src.services import identity_context, untrusted
from src.services.internal_token import is_exposed_without_token

logger = logging.getLogger(__name__)

PREVIEW_CHARS = 80
MAX_HITS = 50
_NOTE_ID = re.compile(r"[0-9a-f]{32}")
_NOT_AVAILABLE = "No note with that id is available to agents. List the notes first and use an id from the list."


class NotesError(Exception):
    """The call cannot be answered; the message is for the caller to relay."""


def open_gateway() -> NotesGateway:
    return NotesGateway(
        settings.db_gateway_url,
        settings.db_gateway_instance,
        settings.db_gateway_connection,
        settings.internal_api_token,
    )


def _owner() -> str:
    """The caller's account uid, after checking that the identity can be trusted at all."""
    if is_exposed_without_token(settings.host, settings.internal_api_token):
        # Without the token any machine that can reach the port could claim any uid.
        raise NotesError(
            f"Notes are disabled: this server listens on {settings.host!r} without INTERNAL_API_TOKEN, "
            "so anyone on the network could read notes. Set INTERNAL_API_TOKEN, or bind to 127.0.0.1."
        )
    uid = identity_context.current_uid()
    if not uid:
        raise NotesError("Notes need a signed-in user, and this call carried no identity.")
    return uid


def _readable(gateway: NotesGateway, owner: str) -> list[dict[str, Any]]:
    try:
        docs = gateway.readable_by_agents(owner)
    except NotesGatewayError as error:
        logger.warning("notes: %s", error)
        raise NotesError(f"Notes are unavailable right now: {error}") from error
    # The gateway already filtered; check again so a backend that ignored a filter cannot leak a note.
    return [d for d in docs if d.get("owner") == owner and d.get("agent_readable") is True]


def _tags(doc: dict[str, Any]) -> list[str]:
    tags = doc.get("tags")
    return [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []


def _updated(doc: dict[str, Any]) -> str:
    return str(doc.get("updated_at", ""))[:10]


def _preview(doc: dict[str, Any]) -> str:
    return " ".join(str(doc.get("body", "")).split())[:PREVIEW_CHARS]


def list_notes(gateway: NotesGateway, tag: str = "") -> NoteListResult:
    wanted = tag.strip().lower()
    docs = _readable(gateway, _owner())
    if wanted:
        docs = [d for d in docs if wanted in _tags(d)]
    notes = [
        NoteSummary(
            id=str(d["id"]), title=str(d.get("title", "")), tags=", ".join(_tags(d)),
            updated=_updated(d), preview=_preview(d),
        )
        for d in docs
    ]
    if not notes:
        what = f"tagged {wanted!r} " if wanted else ""
        return NoteListResult(count=0, notes=[], message=f"No notes {what}are shared with agents.")
    return NoteListResult(count=len(notes), notes=notes, message=f"{len(notes)} note(s) shared with agents.")


def search(gateway: NotesGateway, query: str) -> NoteSearchResult:
    needle = query.strip().lower()
    if not needle:
        raise NotesError("Say what to search for.")
    hits: list[NoteHit] = []
    for doc in _readable(gateway, _owner()):
        title = str(doc.get("title", ""))
        line = next((ln.strip() for ln in str(doc.get("body", "")).splitlines() if needle in ln.lower()), "")
        if line or needle in title.lower():
            hits.append(NoteHit(id=str(doc["id"]), title=title, line=line[:200] or title))
        if len(hits) >= MAX_HITS:
            break
    if not hits:
        return NoteSearchResult(query=query, count=0, hits=[], message="No shared note matches.")
    return NoteSearchResult(query=query, count=len(hits), hits=hits, message=f"{len(hits)} shared note(s) match.")


def read_note(gateway: NotesGateway, note_id: str) -> NoteResult:
    owner = _owner()
    key = note_id.strip().lower()
    if not _NOTE_ID.fullmatch(key):
        raise NotesError(_NOT_AVAILABLE)
    try:
        doc = gateway.get(key)
    except NotesGatewayError as error:
        logger.warning("notes: %s", error)
        raise NotesError(f"Notes are unavailable right now: {error}") from error
    if doc is None or doc.get("owner") != owner or doc.get("agent_readable") is not True:
        raise NotesError(_NOT_AVAILABLE)
    title = str(doc.get("title", ""))
    body = untrusted.fenced_and_capped(str(doc.get("body", "")), source="your note")
    return NoteResult(
        id=key, title=title, tags=", ".join(_tags(doc)), updated=_updated(doc), content=body,
        message=f"Read note {title!r}.",
    )
