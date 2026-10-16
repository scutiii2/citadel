"""Typed operations on the notes a user let agents use.

ember_api owns the notes and db_gateway stores them. This reads and changes them for the
asking account only (`identity_context.current_uid()` is ember's account uid, the same
value ember_api stores as a note's owner) and only the notes whose `agent_readable`
switch is on. Anything else, including another account's note and a note whose switch is
off, is reported as "no such note" so a caller cannot tell the difference.

Agents can create a note, change one that is already shared, and append to it. They cannot
delete a note or change its switch. The limits below repeat ember_api's
(`apps/Ember/ember_api/src/services/notes.py`); change them together.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from src.capabilities.notes.contract import (
    NoteHit,
    NoteListResult,
    NoteResult,
    NoteSearchResult,
    NoteSummary,
    NoteWriteResult,
)
from src.capabilities.notes.utils.gateway import MAX_NOTES, NotesGateway, NotesGatewayError
from src.config import settings
from src.services import identity_context, untrusted
from src.services.internal_token import is_exposed_without_token

logger = logging.getLogger(__name__)

PREVIEW_CHARS = 80
MAX_HITS = 50
TITLE_MAX = 200
BODY_MAX = 20_000
TAG_MAX = 30
MAX_TAGS = 10
_NOTE_ID = re.compile(r"[0-9a-f]{32}")
_TAG = re.compile(r"[a-z0-9][a-z0-9_-]*")
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


# ---- writing ----


def _parse_tags(raw: str) -> list[str]:
    """Comma-separated tags: trimmed, lowercase, repeats and empty entries dropped. The same
    rules ember_api enforces, so a note an agent writes opens cleanly on the Notes page."""
    tags: list[str] = []
    for item in raw.split(","):
        tag = item.strip().lower()
        if not tag:
            continue
        if len(tag) > TAG_MAX or not _TAG.fullmatch(tag):
            raise NotesError(
                f"The tag {item.strip()!r} is not allowed: a tag is 1 to {TAG_MAX} characters of letters, "
                "digits, - and _, and does not start with - or _."
            )
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise NotesError(f"A note can have at most {MAX_TAGS} tags.")
    return tags


def _title(raw: str) -> str:
    title = raw.strip()
    if not title:
        raise NotesError("A note needs a title.")
    if len(title) > TITLE_MAX:
        raise NotesError(f"A title is at most {TITLE_MAX} characters; this one has {len(title)}.")
    return title


def _body(text: str) -> str:
    if len(text) > BODY_MAX:
        raise NotesError(f"A note holds at most {BODY_MAX} characters; this text has {len(text)}.")
    return text


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _fetch_editable(gateway: NotesGateway, owner: str, note_id: str) -> tuple[str, dict[str, Any]]:
    """(key, document) of a note the agent may change: the caller's own and shared with agents."""
    key = note_id.strip().lower()
    if not _NOTE_ID.fullmatch(key):
        raise NotesError(_NOT_AVAILABLE)
    doc = _call(gateway.get, key)
    if doc is None or doc.get("owner") != owner or doc.get("agent_readable") is not True:
        raise NotesError(_NOT_AVAILABLE)
    return key, doc


def _call(fn, *args):
    try:
        return fn(*args)
    except NotesGatewayError as error:
        logger.warning("notes: %s", error)
        raise NotesError(f"Notes are unavailable right now: {error}") from error


def _written(key: str, doc: dict[str, Any], verb: str) -> NoteWriteResult:
    title = str(doc.get("title", ""))
    return NoteWriteResult(
        id=key, title=title, tags=", ".join(_tags(doc)),
        message=f"{verb} note {title!r} (id {key}). It is marked as last edited by an agent.",
    )


def create_note(gateway: NotesGateway, title: str, body: str, tags: str = "") -> NoteWriteResult:
    owner = _owner()
    doc_title, doc_body, doc_tags = _title(title), _body(body), _parse_tags(tags)
    if _call(gateway.count_owned, owner) >= MAX_NOTES:
        raise NotesError(f"The user already has {MAX_NOTES} notes, the most allowed. Ask them to delete one.")
    now = _now()
    doc = {
        "id": uuid.uuid4().hex, "owner": owner, "title": doc_title, "body": doc_body, "tags": doc_tags,
        # Shared from the start: the user asked an agent to write it, and agents can then keep working on it.
        "agent_readable": True, "last_editor": "agent", "created_at": now, "updated_at": now,
    }
    _call(gateway.put, doc["id"], doc)
    logger.info("notes: an agent created a note for account %s", owner)
    return _written(doc["id"], doc, "Created")


def update_note(gateway: NotesGateway, note_id: str, title: str = "", body: str = "", tags: str = "") -> NoteWriteResult:
    """Replaces the title, text or tags that are given; an empty argument leaves that part as it is."""
    owner = _owner()
    if not (title.strip() or body or tags.strip()):
        raise NotesError("Nothing to change: give a new title, text or tags.")
    key, doc = _fetch_editable(gateway, owner, note_id)
    if title.strip():
        doc["title"] = _title(title)
    if body:
        doc["body"] = _body(body)
    if tags.strip():
        doc["tags"] = _parse_tags(tags)
    doc.update(last_editor="agent", updated_at=_now())
    _call(gateway.put, key, doc)
    logger.info("notes: an agent changed a note of account %s", owner)
    return _written(key, doc, "Updated")


def append_to_note(gateway: NotesGateway, note_id: str, text: str) -> NoteWriteResult:
    owner = _owner()
    if not text.strip():
        raise NotesError("Nothing to add: the text is empty.")
    key, doc = _fetch_editable(gateway, owner, note_id)
    body = str(doc.get("body", ""))
    joined = body.rstrip("\n") + "\n" + text if body.strip() else text
    if len(joined) > BODY_MAX:
        raise NotesError(
            f"The note would pass {BODY_MAX} characters ({BODY_MAX - len(body)} left; the text is {len(text)}). "
            "Add less, or create a new note."
        )
    doc.update(body=joined, last_editor="agent", updated_at=_now())
    _call(gateway.put, key, doc)
    logger.info("notes: an agent added to a note of account %s", owner)
    return _written(key, doc, "Added to")
