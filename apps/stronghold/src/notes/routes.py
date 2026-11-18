"""/notes: an account's private notes, kept in Treasury. A note is visible only to its owner.

Portcullis serves these as /api/notes after checking the login and the chat.use permission.
Armory's notes tools read the same collection for the notes an account shared with agents."""

from __future__ import annotations

from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field, StringConstraints, field_validator

from src.agents.directory import AgentDirectory
from src.agents.gateway import AgentGateway, Caller
from src.document_store import DbGatewayError, DocumentStore
from src.notes.store import (
    BODY_MAX,
    TITLE_MAX,
    Note,
    NoteChanged,
    NoteLimit,
    NoteNotFound,
    NotesService,
    normalize_tags,
    purge_owner,
)
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.notes.tag_suggestions import TagSuggester, TagSuggestionUnavailable
from src.notes.tag_writer import TagWriter, TagWriterUnavailable

router = APIRouter(prefix="/notes", tags=["notes"])
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]


def get_notes_service(request: Request, requester: Requester = Depends(current_requester)) -> NotesService:
    return NotesService(request.app.state.store, requester.uid)


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


def get_agent_gateway(request: Request) -> AgentGateway:
    return request.app.state.agent_gateway


def get_agent_directory(request: Request) -> AgentDirectory:
    return request.app.state.agents


class NoteBody(BaseModel):
    title: Title
    body: str = Field(default="", max_length=BODY_MAX)
    tags: list[str] = Field(default_factory=list, max_length=50)
    agent_readable: bool = False

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return normalize_tags(tags)


class NoteUpdate(NoteBody):
    # The updated_at of the version the editor opened; the save is refused (412) if the note changed since.
    expected_updated_at: str | None = Field(default=None, max_length=64)


class NoteOut(BaseModel):
    id: str
    title: str
    body: str
    tags: list[str]
    agent_readable: bool
    last_editor: Literal["user", "agent"]
    created_at: str
    updated_at: str

    @classmethod
    def of(cls, note: Note) -> NoteOut:
        return cls(
            id=note.id, title=note.title, body=note.body, tags=list(note.tags),
            agent_readable=note.agent_readable, last_editor=note.last_editor,
            created_at=note.created_at, updated_at=note.updated_at,
        )


class TagOut(BaseModel):
    tag: str
    count: int


class SuggestBody(BaseModel):
    """The note as the editor holds it (maybe not saved yet)."""

    title: str = Field(default="", max_length=TITLE_MAX)
    body: str = Field(default="", max_length=BODY_MAX)
    tags: list[str] = Field(default_factory=list, max_length=50)


class SuggestionsOut(BaseModel):
    suggested: list[str]
    checked: int
    skipped: int


class GeneratedTagsOut(BaseModel):
    tags: list[str]


async def _log_agent_access(platform: PortcullisClient, requester: Requester, allowed: bool) -> None:
    # Only the switch is logged, never the note's text.
    await platform.log_action(
        requester.uid, "notes.agent_access", "Let agents read a note" if allowed else "Stopped agents reading a note"
    )


def _fail(error: Exception) -> NoReturn:
    if isinstance(error, NoteNotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found") from error
    if isinstance(error, NoteLimit):
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if isinstance(error, NoteChanged):
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "This note changed since you opened it") from error
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


@router.post("/suggest-tags")
async def suggest_tags(
    body: SuggestBody,
    requester: Requester = Depends(current_requester),
    notes: NotesService = Depends(get_notes_service),
    gateway: AgentGateway = Depends(get_agent_gateway),
    directory: AgentDirectory = Depends(get_agent_directory),
) -> SuggestionsOut:
    """Which of the account's existing tags (not on the note yet) Laya thinks fit it."""
    try:
        have = {tag.strip().lower() for tag in body.tags}
        candidates = [tag for tag, _count in await notes.tags() if tag not in have]
    except DbGatewayError as error:
        _fail(error)
    caller = Caller(username=requester.username, email=requester.email, uid=requester.uid)
    try:
        found = await TagSuggester(gateway, directory).suggest(caller, body.title, body.body, candidates)
    except TagSuggestionUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Tag suggestions are unavailable: {error}") from error
    return SuggestionsOut(suggested=found.suggested, checked=found.checked, skipped=found.skipped)


@router.post("/generate-tag")
async def generate_tag(
    body: SuggestBody,
    requester: Requester = Depends(current_requester),
    notes: NotesService = Depends(get_notes_service),
    gateway: AgentGateway = Depends(get_agent_gateway),
    directory: AgentDirectory = Depends(get_agent_directory),
) -> GeneratedTagsOut:
    """Up to three new tags for the note, written by the tag-writer agent. Nothing is applied."""
    try:
        known = [tag for tag, _count in await notes.tags()]
    except DbGatewayError as error:
        _fail(error)
    caller = Caller(username=requester.username, email=requester.email, uid=requester.uid)
    try:
        tags = await TagWriter(gateway, directory).generate(caller, body.title, body.body, known, body.tags)
    except TagWriterUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Tag generation is unavailable: {error}") from error
    return GeneratedTagsOut(tags=tags)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteBody,
    requester: Requester = Depends(current_requester),
    notes: NotesService = Depends(get_notes_service),
    platform: PortcullisClient = Depends(get_platform),
) -> NoteOut:
    try:
        note = await notes.create(body.title, body.body, body.tags, body.agent_readable)
    except (NoteLimit, DbGatewayError) as error:
        _fail(error)
    await platform.log_action(requester.uid, "notes.create", "Created a note")
    if note.agent_readable:
        await _log_agent_access(platform, requester, True)
    return NoteOut.of(note)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")], request: Request) -> Response:
    """Every note of a deleted account. Portcullis calls it when an administrator deletes the account."""
    store: DocumentStore = request.app.state.store
    try:
        await purge_owner(store, uid)
    except DbGatewayError as error:
        _fail(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{note_id}")
async def read_note(note_id: str, notes: NotesService = Depends(get_notes_service)) -> NoteOut:
    try:
        return NoteOut.of(await notes.get(note_id))
    except (NoteNotFound, DbGatewayError) as error:
        _fail(error)


@router.put("/{note_id}")
async def update_note(
    note_id: str,
    body: NoteUpdate,
    requester: Requester = Depends(current_requester),
    notes: NotesService = Depends(get_notes_service),
    platform: PortcullisClient = Depends(get_platform),
) -> NoteOut:
    try:
        was_readable = (await notes.get(note_id)).agent_readable
        note = await notes.update(
            note_id, body.title, body.body, body.tags, body.agent_readable, body.expected_updated_at
        )
    except (NoteNotFound, NoteChanged, DbGatewayError) as error:
        _fail(error)
    await platform.log_action(requester.uid, "notes.update", "Edited a note")
    if note.agent_readable != was_readable:
        await _log_agent_access(platform, requester, note.agent_readable)
    return NoteOut.of(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    requester: Requester = Depends(current_requester),
    notes: NotesService = Depends(get_notes_service),
    platform: PortcullisClient = Depends(get_platform),
) -> Response:
    try:
        await notes.delete(note_id)
    except (NoteNotFound, DbGatewayError) as error:
        _fail(error)
    await platform.log_action(requester.uid, "notes.delete", "Deleted a note")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
