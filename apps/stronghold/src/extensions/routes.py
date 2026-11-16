"""/user-extensions: the account's own MCP servers ("private extensions"). Private to the account:
another account's slug is 404. Portcullis checks the permission (chat.use to read,
extensions.personal.manage to change) and serves it as /api/user-extensions.

Each reply carries the extension's live status and tools (from Legion, cached for a minute) and the
NAMES of its headers; a header value is never sent back. `GET /for-turn` is the one place the
values leave: what a chat turn hands to Legion."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field, model_validator

from src.agents.directory import AgentDirectory
from src.agents.gateway import Caller
from src.document_store import DbGatewayError
from src.extensions.probe import ExtensionProbe, ProbeResult
from src.extensions.service import (
    MAX_SLUG,
    SLUG_PATTERN,
    ExtensionLimit,
    ExtensionNotFound,
    InvalidExtension,
    StoredExtension,
    UserExtensionService,
    purge_owner,
)
from src.requester import Requester, current_requester

router = APIRouter(prefix="/user-extensions", tags=["user-extensions"])

NOT_PROBED = ProbeResult("unknown", None, ())


def get_service(request: Request, who: Requester = Depends(current_requester)) -> UserExtensionService:
    return UserExtensionService(request.app.state.store, who.uid, request.app.state.box)


def get_probe(request: Request) -> ExtensionProbe:
    return request.app.state.extension_probe


def get_directory(request: Request) -> AgentDirectory:
    return request.app.state.agents


class ExtensionCreate(BaseModel):
    label: str = Field(max_length=200)
    url: str = Field(max_length=2000)
    description: str = Field(default="", max_length=1000)
    headers: dict[str, str] | None = None


class ExtensionUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=1000)
    # When present (even empty) it replaces every header; the browser sends it only if the user retyped them.
    headers: dict[str, str] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def something_to_change(self) -> ExtensionUpdate:
        if not self.model_fields_set:
            raise ValueError("send something to change")
        return self


class ExtensionOut(BaseModel):
    id: str
    label: str
    description: str
    url: str
    header_names: list[str]
    enabled: bool
    status: str
    error: str | None
    tools: list[str]

    @classmethod
    def of(cls, stored: StoredExtension, probe: ProbeResult) -> ExtensionOut:
        row = stored.row
        return cls(id=row.slug, label=row.label, description=row.description, url=row.url,
                   header_names=stored.header_names, enabled=row.enabled, status=probe.status,
                   error=probe.error, tools=list(probe.tools))


class TurnOut(BaseModel):
    items: list[dict[str, Any]]
    skipped: list[dict[str, Any]]


async def _probe(stored: StoredExtension, who: Requester, probe: ExtensionProbe, directory: AgentDirectory) -> ProbeResult:
    if not stored.row.enabled:
        return NOT_PROBED
    agent = await directory.entry()
    return await probe.check(agent.url if agent else None, Caller(who.username, who.email, who.uid), who.uid, stored)


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Private extensions storage is unavailable")


@router.get("")
async def list_extensions(who: Requester = Depends(current_requester), service: UserExtensionService = Depends(get_service),
                          probe: ExtensionProbe = Depends(get_probe),
                          directory: AgentDirectory = Depends(get_directory)) -> list[ExtensionOut]:
    try:
        stored = await service.list()
    except DbGatewayError as error:
        raise _unavailable() from error
    results = await asyncio.gather(*(_probe(item, who, probe, directory) for item in stored))
    return [ExtensionOut.of(item, result) for item, result in zip(stored, results)]


@router.get("/for-turn")
async def for_turn(service: UserExtensionService = Depends(get_service)) -> TurnOut:
    """The enabled extensions with their headers, for a chat turn (internal: Portcullis never passes it to a browser)."""
    try:
        turn = await service.enabled_for_turn()
    except DbGatewayError as error:
        raise _unavailable() from error
    return TurnOut(items=list(turn.items), skipped=list(turn.skipped))


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_extension(body: ExtensionCreate, who: Requester = Depends(current_requester),
                        service: UserExtensionService = Depends(get_service), probe: ExtensionProbe = Depends(get_probe),
                        directory: AgentDirectory = Depends(get_directory)) -> ExtensionOut:
    """Saves the extension (even if it cannot be reached right now) and probes it once."""
    try:
        stored = await service.create(label=body.label, url=body.url, description=body.description, headers=body.headers)
    except InvalidExtension as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except ExtensionLimit as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have added as many private extensions as allowed") from error
    except DbGatewayError as error:
        raise _unavailable() from error
    return ExtensionOut.of(stored, await _probe(stored, who, probe, directory))


@router.patch("/{slug}")
async def update_extension(body: ExtensionUpdate, slug: str = Path(pattern=SLUG_PATTERN, max_length=MAX_SLUG),
                           who: Requester = Depends(current_requester), service: UserExtensionService = Depends(get_service),
                           probe: ExtensionProbe = Depends(get_probe),
                           directory: AgentDirectory = Depends(get_directory)) -> ExtensionOut:
    try:
        stored = await service.update(slug, label=body.label, description=body.description, url=body.url,
                                      headers=body.headers, enabled=body.enabled)
    except ExtensionNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such extension") from error
    except InvalidExtension as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except DbGatewayError as error:
        raise _unavailable() from error
    if body.url is not None or body.headers is not None:
        probe.forget(who.uid, slug)
    return ExtensionOut.of(stored, await _probe(stored, who, probe, directory))


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_extension(slug: str = Path(pattern=SLUG_PATTERN, max_length=MAX_SLUG), who: Requester = Depends(current_requester),
                           service: UserExtensionService = Depends(get_service),
                           probe: ExtensionProbe = Depends(get_probe)) -> Response:
    try:
        await service.delete(slug)
    except ExtensionNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such extension") from error
    except DbGatewayError as error:
        raise _unavailable() from error
    probe.forget(who.uid, slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")], request: Request) -> Response:
    """A deleted account's extensions. Portcullis calls it when an administrator deletes the account."""
    await purge_owner(request.app.state.store, uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
