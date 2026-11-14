"""Authenticated brain settings and browsing; internal snapshots never reach browsers."""
import hmac
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from src.deps import current_account, get_db_gateway, get_secret_box, get_db_session, get_settings, require_permission, get_agent_gateway
from src.models import Account
from src.services.brain_connections import BrainConnections, BrainError, ConnectionInput, PUBLISH
from src.services.brain_gateway import BrainGateway
from src.services.brain_promotions import Promotions, PublicationInput, note_hash
from src.services import brain_suggestions
from src.services.notes import NotesService
from src.services.agent_gateway import Caller, AgentCallError
from src.routes.mcp import get_agent_directory
from src.services.usage_service import UsageService

router = APIRouter(prefix="/api/brains", tags=["brains"])
Scope = Literal["instance", "personal"]


def connections(store=Depends(get_db_gateway), box=Depends(get_secret_box)):
    return BrainConnections(store, box)


def gateway(request: Request):
    return BrainGateway(request.app.state.upstream, request.app.state.settings.mcp_server_url,
                        request.app.state.internal_token)


async def valid_account(account=Depends(current_account), settings=Depends(get_settings)):
    if settings.require_email_verification and not account.email_verified:
        raise HTTPException(403, "Email not verified")
    return account


def _manage(scope, account):
    if scope == "instance" and "settings.manage" not in account.permission_names:
        raise HTTPException(403, "Missing permission: settings.manage")


@router.get("/connections/{scope}")
async def get_connection(scope: Scope, account=Depends(valid_account), service=Depends(connections)):
    _manage(scope, account)
    return await service.get(scope, account.uid)


@router.put("/connections/{scope}")
async def save_connection(scope: Scope, body: ConnectionInput, request: Request,
                          account=Depends(valid_account), service=Depends(connections), remote=Depends(gateway)):
    _manage(scope, account)
    result = await service.save(scope, account.uid, body)
    try:
        await remote.operation(account.uid, "retire", scope)
    except BrainError:
        pass  # Resolver revocation is immediate even when Armory is unreachable.
    await request.app.state.logs.action(account, "brain.connection_save", f"scope={scope}; revision={result['revision']}")
    return result


@router.post("/connections/{scope}/test")
async def test_connection(scope: Scope, body: ConnectionInput, account=Depends(valid_account),
                          service=Depends(connections), remote=Depends(gateway)):
    _manage(scope, account)
    candidate = await service.candidate(scope, account.uid, body)
    return await remote.operation(account.uid, "test", scope, candidate=service.snapshot(candidate))


@router.get("/destinations")
async def destinations(account=Depends(valid_account), service=Depends(connections)):
    results = []
    for scope in ("personal", "instance"):
        row = await service.get(scope, account.uid)
        # Instance endpoint and credentials belong in staff settings only.
        results.append({k: row[k] for k in ("id", "scope", "label", "enabled", "revision", "generation", "folder", "status")} | {
            "writable": row["enabled"] and (row["allow_write"] or row["status"] == "legacy") and (scope == "personal" or PUBLISH in account.permission_names)})
    return results


class ResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Scope
    operation: Literal["read", "list", "search", "status", "write", "append"]


@router.post("/internal/resolve")
async def resolve_connection(body: ResolveBody, request: Request, service=Depends(connections),
                             session=Depends(get_db_session), settings=Depends(get_settings)):
    token = request.app.state.internal_token
    if not token or not hmac.compare_digest(token, request.headers.get("X-Internal-Token", "")):
        raise HTTPException(401, "Valid internal authentication required")
    uid = request.headers.get("X-Requester-Uid", "")
    account = await session.scalar(select(Account).where(Account.uid == uid)) if uid else None
    if account is None or not account.is_active or settings.require_email_verification and not account.email_verified:
        raise HTTPException(403, "A valid signed-in requester is required")
    return await service.resolve(body.scope, account.uid, write=body.operation in {"write", "append"},
                                 publish=PUBLISH in account.permission_names)


class BrowseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["instance", "personal", "both"] = "instance"
    operation: Literal["list", "read", "search", "status"]
    path: str = Field(default="", max_length=500)
    query: str = Field(default="", max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/browse")
async def browse(body: BrowseBody, account=Depends(valid_account), remote=Depends(gateway)):
    return await remote.operation(account.uid, body.operation, body.scope,
                                  path=body.path, query=body.query, top_k=body.top_k)




def promotions(account=Depends(require_permission("chat.use")), service=Depends(connections), remote=Depends(gateway)):
    return Promotions(service.store, service, remote, account.uid, publish=PUBLISH in account.permission_names)


@router.get("/promotions")
async def list_promotions(service=Depends(promotions)):
    return await service.list()


@router.get("/notes/{note_id}/review")
async def review_publication(note_id: str, account=Depends(require_permission("chat.use")), service=Depends(connections)):
    from src.services.notes import NoteNotFound
    try:
        note = await NotesService(service.store, account.uid).get(note_id)
    except NoteNotFound:
        raise BrainError("Note not found", 404) from None
    return {"note_id": note.id, "title": note.title, "body": note.body,
            "source_hash": note_hash(note), "source_revision": note.updated_at, "agent_readable": note.agent_readable}


@router.post("/notes/{note_id}/promote")
async def publish_note(note_id: str, body: PublicationInput, request: Request,
                       account=Depends(require_permission("chat.use")), service=Depends(promotions)):
    result = await service.publish(note_id, body)
    await request.app.state.logs.action(account, "brain.publish", f"promotion={result['id']}; scope={body.scope}")
    return result


@router.post("/promotions/{promotion_id}/reconcile")
async def reconcile_publication(promotion_id: str, service=Depends(promotions)):
    return await service.reconcile(promotion_id)


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_ids: list[str] = Field(default_factory=list, max_length=20)
    explicit_private: list[str] = Field(default_factory=list, max_length=20)


@router.post("/suggestions/review")
async def review_notes(body: ReviewBody, request: Request, account=Depends(require_permission("chat.use")),
                       service=Depends(connections), session=Depends(get_db_session),
                       settings=Depends(get_settings), agent_gateway=Depends(get_agent_gateway),
                       directory=Depends(get_agent_directory)):
    notes_service = NotesService(service.store, account.uid)
    notes = await brain_suggestions.eligible_notes(notes_service, body.note_ids, body.explicit_private)
    snapshots = {}
    for scope in ("personal", "instance"):
        try:
            snapshots[scope] = await service.resolve(scope, account.uid, write=True, publish=PUBLISH in account.permission_names)
        except BrainError:
            continue
    if not snapshots:
        raise BrainError("Configure a writable brain destination before reviewing promotions")
    if not notes:
        return []
    usage = UsageService(session, settings.usage)
    blocked = await usage.check(account.id)
    if blocked:
        raise BrainError(blocked.reason, 429)
    agent = await directory.entry()
    if agent is None:
        raise BrainError("The interpretation agent is unavailable", 503)
    try:
        result = await agent_gateway.interpret(agent.url, Caller(account.username, account.email, account.uid),
            brain_suggestions.review_prompt(notes, [{"scope": s, "label": d["label"], "folder": d["folder"]} for s, d in snapshots.items()]))
    except AgentCallError:
        raise BrainError("AI promotion review is unavailable. Manual promotion remains available.", 503) from None
    # Account for the actual call even when its output fails validation.
    await usage.record(account.id, uuid.uuid4().hex, "brain_suggestions", None, result)
    items = brain_suggestions.parse_suggestions(str(result.get("response", "")), {n.id for n in notes}, set(snapshots))
    current = {n.id: n for n in await notes_service.list()}
    if any(n.id not in current or note_hash(current[n.id]) != note_hash(n) or current[n.id].updated_at != n.updated_at for n in notes):
        raise BrainError("A Note changed during review. Review the new version.", 412)
    for scope, before in snapshots.items():
        after = await service.resolve(scope, account.uid, write=True, publish=PUBLISH in account.permission_names)
        if before["generation"] != after["generation"]:
            raise BrainError("A destination changed during review. Review again.", 412)
    return await brain_suggestions.store_suggestions(service.store, account.uid, items, notes, snapshots)


@router.get("/suggestions")
async def list_suggestions(account=Depends(require_permission("chat.use")), service=Depends(connections)):
    rows = await service.store.query(brain_suggestions.COLLECTION, {"owner": account.uid}, limit=500)
    notes = {n.id: n for n in await NotesService(service.store, account.uid).list()}
    results = []
    for row in rows:
        note = notes.get(row["note_id"])
        if row.get("owner") != account.uid or row["status"] == "dismissed" or note is None or note_hash(note) != row["source_hash"] or note.updated_at != row["source_revision"]:
            continue
        try:
            dest = await service.resolve(row["scope"], account.uid, write=True, publish=PUBLISH in account.permission_names)
        except BrainError:
            continue
        if dest["generation"] == row["generation"]:
            results.append({k: v for k, v in row.items() if k != "owner"})
    return results


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, account=Depends(require_permission("chat.use")), service=Depends(connections)):
    row = await service.store.get(brain_suggestions.COLLECTION, suggestion_id)
    if row is None or row.get("owner") != account.uid:
        raise BrainError("Suggestion not found", 404)
    await service.store.put(brain_suggestions.COLLECTION, suggestion_id, {**row, "status": "dismissed"})
    return {"status": "dismissed"}
