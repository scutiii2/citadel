"""/brains: personal connections, browsing, publishing Notes and promotion suggestions.

Portcullis serves these as /api/brains after checking the login. What an account may do is asked of
Portcullis on each request (`/internal/accounts/{uid}/permissions`), so a permission taken away
applies at once, and Armory's own resolve call (`POST /brains/resolve`, uid only) is checked the same way.
The resolver exports only personal credentials to Armory. Instance resolution returns authorization.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from src.agents.directory import AgentDirectory
from src.agents.gateway import AgentCallError, AgentGateway, Caller
from src.brains import suggestions as brain_suggestions
from src.brains.connections import PUBLISH, BrainConnections, BrainError, ConnectionInput, purge_owner
from src.brains.gateway import BrainGateway
from src.brains.promotions import Promotions, PublicationInput, note_hash
from src.citadel_auth import current_caller
from src.notes.store import NoteNotFound, NotesService
from src.platform import PlatformError
from src.requester import Requester, current_requester
from src.usage.rows import stored_rows
from src.usage.service import UsageService

router = APIRouter(prefix="/brains", tags=["brains"])
Scope = Literal["instance", "personal"]
CHAT_USE = "chat.use"
SETTINGS_MANAGE = "settings.manage"


def connections(request: Request) -> BrainConnections:
    return BrainConnections(request.app.state.store, request.app.state.box, request.app.state.brain_gateway)


def gateway(request: Request) -> BrainGateway:
    return request.app.state.brain_gateway


async def permissions(request: Request, who: Requester = Depends(current_requester)) -> set[str]:
    """What the account may do now. Refused for an account that is unknown, inactive or unverified."""
    try:
        granted = await request.app.state.platform.permissions(who.uid)
    except PlatformError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Portcullis is unavailable") from None
    if granted is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid signed-in requester is required")
    return granted


def need(granted: set[str], permission: str) -> None:
    if permission not in granted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")


async def _log(request: Request, who: Requester, action: str, message: str) -> None:
    await request.app.state.platform.log_action(who.uid, action, message)


@router.get("/connections/personal")
async def get_connection(who: Requester = Depends(current_requester), granted: set[str] = Depends(permissions),
                         service: BrainConnections = Depends(connections)):
    return await service.get("personal", who.uid)


@router.put("/connections/personal")
async def save_connection(body: ConnectionInput, request: Request, who: Requester = Depends(current_requester),
                          granted: set[str] = Depends(permissions), service: BrainConnections = Depends(connections),
                          remote: BrainGateway = Depends(gateway)):
    result = await service.save("personal", who.uid, body)
    try:
        await remote.operation(who.uid, "retire", "personal")
    except BrainError:
        pass  # Resolver revocation is immediate even when Armory is unreachable.
    await _log(request, who, "brain.connection_save", f"scope=personal; revision={result['revision']}")
    return result


@router.post("/connections/personal/test")
async def test_connection(body: ConnectionInput, who: Requester = Depends(current_requester),
                          granted: set[str] = Depends(permissions), service: BrainConnections = Depends(connections),
                          remote: BrainGateway = Depends(gateway)):
    candidate = await service.candidate("personal", who.uid, body)
    return await remote.operation(who.uid, "test", "personal", candidate=service.snapshot(candidate))


@router.get("/destinations")
async def destinations(who: Requester = Depends(current_requester), granted: set[str] = Depends(permissions),
                       service: BrainConnections = Depends(connections)):
    results = []
    for scope in ("personal", "instance"):
        if scope == "instance":
            try:
                row = await service.get(scope, who.uid)
            except BrainError:
                row = {**BrainConnections.public(None, scope), "enabled": False, "status": "unavailable", "writable": False}
            writable = row["writable"] is True and PUBLISH in granted
        else:
            row = await service.get(scope, who.uid)
            writable = row["enabled"] and row["allow_write"]
        results.append({k: row[k] for k in ("id", "scope", "label", "enabled", "revision", "generation", "folder", "status")}
                       | {"writable": writable})
    return results


@router.get("/writable/{scope}")
async def writable(scope: Scope, who: Requester = Depends(current_requester), granted: set[str] = Depends(permissions),
                   service: BrainConnections = Depends(connections)) -> dict[str, bool]:
    """Whether the account may write to this destination now (Portcullis asks before an auto-save)."""
    try:
        await service.resolve(scope, who.uid, write=True, publish=PUBLISH in granted)
    except BrainError:
        return {"writable": False}
    return {"writable": True}


class ResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Scope
    operation: Literal["read", "list", "search", "status", "write", "append", "manage"]


@router.post("/resolve")
async def resolve_connection(body: ResolveBody, who: Requester = Depends(current_requester),
                             granted: set[str] = Depends(permissions), service: BrainConnections = Depends(connections)):
    """For Armory: live authorization for shared access, or the requester's personal snapshot."""
    caller = current_caller()
    if caller is None or caller.name != "armory":
        raise HTTPException(403, "Armory service required")
    write = body.operation in {"write", "append"}
    if body.scope == "instance":
        if body.operation == "manage":
            need(granted, SETTINGS_MANAGE)
        elif write:
            need(granted, PUBLISH)
        return {"scope": "instance", "authorized": True}
    if body.operation == "manage":
        raise HTTPException(422, "Choose the Instance Brain for shared settings")
    return await service.resolve("personal", who.uid, write=write, publish=False)


class BrowseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["instance", "personal", "both"] = "instance"
    operation: Literal["list", "read", "search", "status"]
    path: str = Field(default="", max_length=500)
    query: str = Field(default="", max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/browse")
async def browse(body: BrowseBody, who: Requester = Depends(current_requester), _granted: set[str] = Depends(permissions),
                 remote: BrainGateway = Depends(gateway)):
    return await remote.operation(who.uid, body.operation, body.scope, path=body.path, query=body.query, top_k=body.top_k)


async def promotions(request: Request, who: Requester = Depends(current_requester), granted: set[str] = Depends(permissions),
                     service: BrainConnections = Depends(connections), remote: BrainGateway = Depends(gateway)) -> Promotions:
    need(granted, CHAT_USE)
    return Promotions(service.store, service, remote, who.uid, publish=PUBLISH in granted,
                      notes=NotesService(request.app.state.store, who.uid))


@router.get("/promotions")
async def list_promotions(service: Promotions = Depends(promotions)):
    return await service.list()


@router.get("/notes/{note_id}/review")
async def review_publication(note_id: str, request: Request, who: Requester = Depends(current_requester),
                             granted: set[str] = Depends(permissions)):
    need(granted, CHAT_USE)
    try:
        note = await NotesService(request.app.state.store, who.uid).get(note_id)
    except NoteNotFound:
        raise BrainError("Note not found", 404) from None
    return {"note_id": note.id, "title": note.title, "body": note.body,
            "source_hash": note_hash(note), "source_revision": note.updated_at, "agent_readable": note.agent_readable}


@router.post("/notes/{note_id}/promote")
async def publish_note(note_id: str, body: PublicationInput, request: Request, who: Requester = Depends(current_requester),
                       service: Promotions = Depends(promotions)):
    result = await service.publish(note_id, body)
    await _log(request, who, "brain.publish", f"promotion={result['id']}; scope={body.scope}")
    return result


@router.post("/promotions/{promotion_id}/reconcile")
async def reconcile_publication(promotion_id: str, service: Promotions = Depends(promotions)):
    return await service.reconcile(promotion_id)


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_ids: list[str] = Field(default_factory=list, max_length=20)
    explicit_private: list[str] = Field(default_factory=list, max_length=20)


@router.post("/suggestions/review")
async def review_notes(body: ReviewBody, request: Request, who: Requester = Depends(current_requester),
                       granted: set[str] = Depends(permissions), service: BrainConnections = Depends(connections)):
    need(granted, CHAT_USE)
    notes_service = NotesService(request.app.state.store, who.uid)
    notes = await brain_suggestions.eligible_notes(notes_service, body.note_ids, body.explicit_private)
    publish = PUBLISH in granted
    snapshots = {}
    for scope in ("personal", "instance"):
        try:
            snapshots[scope] = await service.resolve(scope, who.uid, write=True, publish=publish)
        except BrainError:
            continue
    if not snapshots:
        raise BrainError("Configure a writable brain destination before reviewing promotions")
    if not notes:
        return []
    usage: UsageService = request.app.state.usage
    blocked = await usage.check(who.uid)
    if blocked:
        raise BrainError(blocked.reason, 429)
    agents: AgentDirectory = request.app.state.agents
    agent = await agents.entry()
    if agent is None:
        raise BrainError("The interpretation agent is unavailable", 503)
    agent_gateway: AgentGateway = request.app.state.agent_gateway
    try:
        result = await agent_gateway.interpret(agent.url, Caller(who.username, who.email, who.uid),
            brain_suggestions.review_prompt(notes, [{"scope": s, "label": d["label"], "folder": d["folder"]} for s, d in snapshots.items()]))
    except AgentCallError:
        raise BrainError("AI promotion review is unavailable. Manual promotion remains available.", 503) from None
    # Account for the actual call even when its output fails validation.
    await usage.record(who.uid, uuid.uuid4().hex, "brain_suggestions", None, stored_rows(result))
    items = brain_suggestions.parse_suggestions(str(result.get("response", "")), {n.id for n in notes}, set(snapshots))
    current = {n.id: n for n in await notes_service.list()}
    if any(n.id not in current or note_hash(current[n.id]) != note_hash(n) or current[n.id].updated_at != n.updated_at for n in notes):
        raise BrainError("A Note changed during review. Review the new version.", 412)
    for scope, before in snapshots.items():
        after = await service.resolve(scope, who.uid, write=True, publish=publish)
        if before["generation"] != after["generation"]:
            raise BrainError("A destination changed during review. Review again.", 412)
    return await brain_suggestions.store_suggestions(service.store, who.uid, items, notes, snapshots)


@router.get("/suggestions")
async def list_suggestions(request: Request, who: Requester = Depends(current_requester),
                           granted: set[str] = Depends(permissions), service: BrainConnections = Depends(connections)):
    need(granted, CHAT_USE)
    rows = await service.store.query(brain_suggestions.COLLECTION, {"owner": who.uid}, limit=500)
    notes = {n.id: n for n in await NotesService(request.app.state.store, who.uid).list()}
    results = []
    for row in rows:
        note = notes.get(row["note_id"])
        if row.get("owner") != who.uid or row["status"] == "dismissed" or note is None or note_hash(note) != row["source_hash"] or note.updated_at != row["source_revision"]:
            continue
        try:
            dest = await service.resolve(row["scope"], who.uid, write=True, publish=PUBLISH in granted)
        except BrainError:
            continue
        if dest["generation"] == row["generation"]:
            results.append({k: v for k, v in row.items() if k != "owner"})
    return results


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, who: Requester = Depends(current_requester),
                             granted: set[str] = Depends(permissions), service: BrainConnections = Depends(connections)):
    need(granted, CHAT_USE)
    row = await service.store.get(brain_suggestions.COLLECTION, suggestion_id)
    if row is None or row.get("owner") != who.uid:
        raise BrainError("Suggestion not found", 404)
    await service.store.put(brain_suggestions.COLLECTION, suggestion_id, {**row, "status": "dismissed"})
    return {"status": "dismissed"}


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")], request: Request,
                        remote: BrainGateway = Depends(gateway)) -> Response:
    """Every brain record of a deleted account, and Armory's derived personal state.
    Portcullis calls it when an administrator deletes the account."""
    await purge_owner(request.app.state.store, uid)
    try:
        await remote.operation(uid, "retire", "personal")
    except BrainError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Personal derived brain state could not be purged") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
