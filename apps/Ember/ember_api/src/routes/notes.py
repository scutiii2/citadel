"""/api/notes: the logged-in account's private notes, kept in db_gateway.
Needs chat.use. A note is visible only to its owner."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints, field_validator

from src.deps import get_db_gateway, get_log_writer, require_permission
from src.models import Account
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.log_service import LogWriter
from src.services.notes import BODY_MAX, TITLE_MAX, Note, NoteLimit, NoteNotFound, NotesService, normalize_tags
from src.services.permissions import CHAT_USE

router = APIRouter(prefix="/api/notes", tags=["notes"])

require_chat = require_permission(CHAT_USE)
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]


def get_notes_service(
    account: Account = Depends(require_chat), store: DocumentStore = Depends(get_db_gateway)
) -> NotesService:
    return NotesService(store, account.uid)


class NoteBody(BaseModel):
    title: Title
    body: str = Field(default="", max_length=BODY_MAX)
    tags: list[str] = Field(default_factory=list, max_length=50)
    agent_readable: bool = False

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return normalize_tags(tags)


class NoteOut(BaseModel):
    id: str
    title: str
    body: str
    tags: list[str]
    agent_readable: bool
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, note: Note) -> NoteOut:
        return cls(
            id=note.id, title=note.title, body=note.body, tags=list(note.tags),
            agent_readable=note.agent_readable, created_at=note.created_at, updated_at=note.updated_at,
        )


class TagOut(BaseModel):
    tag: str
    count: int


async def _log_agent_access(logs: LogWriter, account: Account, allowed: bool) -> None:
    # Only the switch is logged, never the note's text.
    await logs.action(
        account, "notes.agent_access", "Let agents read a note" if allowed else "Stopped agents reading a note"
    )


def _fail(error: Exception) -> NoReturn:
    if isinstance(error, NoteNotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found") from error
    if isinstance(error, NoteLimit):
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Notes storage is unavailable") from error


@router.get("")
async def list_notes(notes: NotesService = Depends(get_notes_service)) -> list[NoteOut]:
    try:
        return [NoteOut.of(n) for n in await notes.list()]
    except DbGatewayError as error:
        _fail(error)


@router.get("/tags")
async def list_tags(notes: NotesService = Depends(get_notes_service)) -> list[TagOut]:
    """The tags the account already uses, most used first (declared before /{note_id})."""
    try:
        return [TagOut(tag=tag, count=count) for tag, count in await notes.tags()]
    except DbGatewayError as error:
        _fail(error)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteBody,
    account: Account = Depends(require_chat),
    notes: NotesService = Depends(get_notes_service),
    logs: LogWriter = Depends(get_log_writer),
) -> NoteOut:
    try:
        note = await notes.create(body.title, body.body, body.tags, body.agent_readable)
    except (NoteLimit, DbGatewayError) as error:
        _fail(error)
    await logs.action(account, "notes.create", "Created a note")
    if note.agent_readable:
        await _log_agent_access(logs, account, True)
    return NoteOut.of(note)


@router.get("/{note_id}")
async def read_note(note_id: str, notes: NotesService = Depends(get_notes_service)) -> NoteOut:
    try:
        return NoteOut.of(await notes.get(note_id))
    except (NoteNotFound, DbGatewayError) as error:
        _fail(error)


@router.put("/{note_id}")
async def update_note(
    note_id: str,
    body: NoteBody,
    account: Account = Depends(require_chat),
    notes: NotesService = Depends(get_notes_service),
    logs: LogWriter = Depends(get_log_writer),
) -> NoteOut:
    try:
        was_readable = (await notes.get(note_id)).agent_readable
        note = await notes.update(note_id, body.title, body.body, body.tags, body.agent_readable)
    except (NoteNotFound, DbGatewayError) as error:
        _fail(error)
    await logs.action(account, "notes.update", "Edited a note")
    if note.agent_readable != was_readable:
        await _log_agent_access(logs, account, note.agent_readable)
    return NoteOut.of(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    account: Account = Depends(require_chat),
    notes: NotesService = Depends(get_notes_service),
    logs: LogWriter = Depends(get_log_writer),
) -> Response:
    try:
        await notes.delete(note_id)
    except (NoteNotFound, DbGatewayError) as error:
        _fail(error)
    await logs.action(account, "notes.delete", "Deleted a note")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
