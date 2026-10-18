"""/api/forge: the logged-in account's Forge workers and group chats (forge.use), the plan
allowlists (settings.manage to change), and the worker WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from src.deps import get_db_session, get_forge, get_log_writer, require_permission
from src.models import Account, ForgeGroup, ForgeWorker
from src.services.forge.connections import WorkerConnection
from src.services.forge.coordinator import GroupBusy
from src.services.forge.events import sse_frame
from src.services.forge.groups import (
    TITLE_MAX,
    AlreadyMember,
    GroupLimitError,
    GroupNotFound,
    GroupService,
    InvalidGroup,
    MemberLimitError,
    MemberRow,
    NotAMember,
    WorkerNotEligible,
)
from src.services.forge.messages import message_event
from src.services.forge.plans import InvalidPlanList, PlanPolicyRegistry
from src.services.forge.protocol import PROVIDERS, Heartbeat, Hello, parse_worker_frame, ready_frame
from src.services.forge.runtime import ForgeRuntime
from src.services.forge.workers import (
    WorkerAuthenticator,
    InvalidWorkerLabel,
    WorkerLabelTaken,
    WorkerLimitError,
    WorkerNotFound,
    WorkerPairingService,
)
from src.services.log_service import LogWriter
from src.services.permissions import FORGE_USE, SETTINGS_MANAGE

router = APIRouter(prefix="/api/forge", tags=["forge"])

require_forge = require_permission(FORGE_USE)
require_settings = require_permission(SETTINGS_MANAGE)


def get_pairing(
    account: Account = Depends(require_forge), session: AsyncSession = Depends(get_db_session)
) -> WorkerPairingService:
    return WorkerPairingService(session, account.id)


def get_groups(
    account: Account = Depends(require_forge), session: AsyncSession = Depends(get_db_session)
) -> GroupService:
    return GroupService(session, account.id, PlanPolicyRegistry(session))


# --- shapes -----------------------------------------------------------------------------


class WorkerOut(BaseModel):
    id: int
    provider: str
    label: str
    reported_plan: str | None
    online: bool
    eligible: bool
    problem: str | None
    last_seen: datetime | None
    created_at: datetime


class CreatedWorkerOut(WorkerOut):
    token: str  # shown once


class MemberOut(BaseModel):
    worker_id: int
    label: str
    provider: str
    folder: str
    online: bool


class GroupOut(BaseModel):
    id: int
    title: str
    mode: str
    relay: bool
    running: bool
    created_at: datetime
    members: list[MemberOut]


class CreateWorkerRequest(BaseModel):
    provider: Literal["claude", "codex"]
    label: str = Field(max_length=24)

    @field_validator("label")
    @classmethod
    def lower(cls, label: str) -> str:
        return label.strip()


class PlansRequest(BaseModel):
    plans: list[str] = Field(max_length=12)


class CreateGroupRequest(BaseModel):
    title: str = Field(max_length=TITLE_MAX)
    # Full auto is only ever switched on afterwards, with a confirmation.
    mode: Literal["ask", "accept_edits", "plan"] = "ask"

    @field_validator("title")
    @classmethod
    def not_blank(cls, title: str) -> str:
        if not title.strip():
            raise ValueError("title must not be blank")
        return title


class UpdateGroupRequest(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    mode: Literal["ask", "accept_edits", "plan", "full_auto"] | None = None
    relay: bool | None = None
    confirm_full_auto: bool = False

    @model_validator(mode="after")
    def valid(self) -> UpdateGroupRequest:
        if self.title is None and self.mode is None and self.relay is None:
            raise ValueError("send a title, a mode or relay")
        if self.mode == "full_auto" and not self.confirm_full_auto:
            raise ValueError("full_auto needs confirm_full_auto: true")
        return self


class InviteRequest(BaseModel):
    worker_id: int
    folder: str = Field(max_length=500)


def _worker_out(worker: ForgeWorker, problem: str | None, forge: ForgeRuntime) -> WorkerOut:
    return WorkerOut(
        id=worker.id,
        provider=worker.provider,
        label=worker.label,
        reported_plan=worker.reported_plan,
        online=forge.registry.is_online(worker.id),
        eligible=problem is None,
        problem=problem,
        last_seen=worker.last_seen,
        created_at=worker.created_at,
    )


def _group_out(group: ForgeGroup, rows: list[MemberRow], forge: ForgeRuntime) -> GroupOut:
    return GroupOut(
        id=group.id,
        title=group.title,
        mode=group.mode,
        relay=group.relay,
        running=forge.coordinator.is_running(group.id),
        created_at=group.created_at,
        members=[
            MemberOut(
                worker_id=row.worker.id,
                label=row.worker.label,
                provider=row.worker.provider,
                folder=row.folder,
                online=forge.registry.is_online(row.worker.id),
            )
            for row in rows
        ],
    )


async def _full_group(groups: GroupService, group_id: int, forge: ForgeRuntime) -> GroupOut:
    return _group_out(await groups.get(group_id), await groups.members(group_id), forge)


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --- plans ------------------------------------------------------------------------------


@router.get("/plans", dependencies=[Depends(require_forge)])
async def get_plans(session: AsyncSession = Depends(get_db_session)) -> dict[str, list[str]]:
    """The eligible plan strings per provider (the Forge page shows why a worker is refused)."""
    return await PlanPolicyRegistry(session).allowed()


@router.put("/plans/{provider}")
async def put_plans(
    provider: str,
    body: PlansRequest,
    account: Account = Depends(require_settings),
    session: AsyncSession = Depends(get_db_session),
    logs: LogWriter = Depends(get_log_writer),
) -> dict[str, list[str]]:
    if provider not in PROVIDERS:
        raise _not_found("Provider")
    try:
        saved = await PlanPolicyRegistry(session).for_provider(provider).set_allowed(body.plans)
    except InvalidPlanList as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await logs.action(account, "forge.plans", f"Set the eligible {provider} plans to: {', '.join(saved) or 'none'}")
    return {"plans": saved}


# --- workers ----------------------------------------------------------------------------


@router.get("/workers")
async def list_workers(
    pairing: WorkerPairingService = Depends(get_pairing),
    session: AsyncSession = Depends(get_db_session),
    forge: ForgeRuntime = Depends(get_forge),
) -> list[WorkerOut]:
    plans = PlanPolicyRegistry(session)
    return [_worker_out(worker, await plans.problem(worker), forge) for worker in await pairing.list()]


@router.post("/workers", status_code=status.HTTP_201_CREATED)
async def create_worker(
    body: CreateWorkerRequest,
    account: Account = Depends(require_forge),
    pairing: WorkerPairingService = Depends(get_pairing),
    session: AsyncSession = Depends(get_db_session),
    forge: ForgeRuntime = Depends(get_forge),
    logs: LogWriter = Depends(get_log_writer),
) -> CreatedWorkerOut:
    try:
        created = await pairing.create(body.provider, body.label)
    except InvalidWorkerLabel as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    except (WorkerLabelTaken, WorkerLimitError) as error:
        message = str(error) if isinstance(error, WorkerLimitError) else "You already have a worker with that label"
        raise HTTPException(status.HTTP_409_CONFLICT, message) from error
    await logs.action(account, "forge.worker.create", f'Paired a {body.provider} worker "{created.worker.label}"')
    problem = await PlanPolicyRegistry(session).problem(created.worker)
    return CreatedWorkerOut(**_worker_out(created.worker, problem, forge).model_dump(), token=created.token)


@router.delete("/workers/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker(
    worker_id: int,
    account: Account = Depends(require_forge),
    pairing: WorkerPairingService = Depends(get_pairing),
    forge: ForgeRuntime = Depends(get_forge),
    logs: LogWriter = Depends(get_log_writer),
) -> Response:
    """Revokes the worker: it leaves every group and its token stops working."""
    try:
        worker = await pairing.delete(worker_id)
    except WorkerNotFound as error:
        raise _not_found("Worker") from error
    connection = forge.registry.get(worker.id)
    if connection is not None:
        await connection.close(4401)
    await logs.action(account, "forge.worker.delete", f'Removed the worker "{worker.label}"')
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- groups -----------------------------------------------------------------------------


@router.get("/groups")
async def list_groups(
    groups: GroupService = Depends(get_groups), forge: ForgeRuntime = Depends(get_forge)
) -> list[GroupOut]:
    return [_group_out(group, await groups.members(group.id), forge) for group in await groups.list()]


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    account: Account = Depends(require_forge),
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
    logs: LogWriter = Depends(get_log_writer),
) -> GroupOut:
    try:
        group = await groups.create(body.title, body.mode)
    except GroupLimitError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except InvalidGroup as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    await logs.action(account, "forge.group.create", f'Created the Forge group "{group.title}"')
    return _group_out(group, [], forge)


@router.get("/groups/{group_id}")
async def get_group(
    group_id: int, groups: GroupService = Depends(get_groups), forge: ForgeRuntime = Depends(get_forge)
) -> GroupOut:
    try:
        return await _full_group(groups, group_id, forge)
    except GroupNotFound as error:
        raise _not_found("Group") from error


@router.patch("/groups/{group_id}")
async def update_group(
    group_id: int,
    body: UpdateGroupRequest,
    account: Account = Depends(require_forge),
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
    logs: LogWriter = Depends(get_log_writer),
) -> GroupOut:
    try:
        await groups.update(group_id, title=body.title, mode=body.mode, relay=body.relay)
        if body.mode == "full_auto":
            await forge.coordinator.post_system(
                group_id, "Full auto mode is on: workers run tools without asking. Turn it off to be asked again."
            )
            await logs.action(account, "forge.group.full_auto", f"Switched Forge group {group_id} to full auto")
        return await _full_group(groups, group_id, forge)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    except InvalidGroup as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    account: Account = Depends(require_forge),
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
    logs: LogWriter = Depends(get_log_writer),
) -> Response:
    try:
        group = await groups.get(group_id)
        if forge.coordinator.is_running(group_id):
            raise HTTPException(status.HTTP_409_CONFLICT, "A worker is still answering. Stop it first.")
        await groups.delete(group_id)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    await logs.action(account, "forge.group.delete", f'Deleted the Forge group "{group.title}"')
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/groups/{group_id}/workers", status_code=status.HTTP_201_CREATED)
async def invite_worker(
    group_id: int,
    body: InviteRequest,
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
) -> GroupOut:
    try:
        await groups.invite(group_id, body.worker_id, body.folder)
        return await _full_group(groups, group_id, forge)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    except WorkerNotFound as error:
        raise _not_found("Worker") from error
    except WorkerNotEligible as error:
        raise HTTPException(status.HTTP_409_CONFLICT, error.reason) from error
    except AlreadyMember as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "That worker is already in this group") from error
    except MemberLimitError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except InvalidGroup as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error


@router.delete("/groups/{group_id}/workers/{worker_id}")
async def remove_worker(
    group_id: int,
    worker_id: int,
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
) -> GroupOut:
    try:
        await groups.remove_member(group_id, worker_id)
        return await _full_group(groups, group_id, forge)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    except NotAMember as error:
        raise _not_found("Worker") from error


# --- chat -------------------------------------------------------------------------------

MESSAGE_MAX = 8000
HELLO_TIMEOUT_SECONDS = 10.0


class MessageRequest(BaseModel):
    text: str = Field(max_length=MESSAGE_MAX)

    @field_validator("text")
    @classmethod
    def not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("text must not be blank")
        return text


class PermissionAnswer(BaseModel):
    allow: bool


@router.get("/groups/{group_id}/messages")
async def list_messages(
    group_id: int,
    after: int = Query(default=0, ge=0),
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
) -> list[dict]:
    try:
        await groups.get(group_id)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    return [message_event(message) for message in await forge.store.list_after(group_id, after)]


@router.post("/groups/{group_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_message(
    group_id: int,
    body: MessageRequest,
    account: Account = Depends(require_forge),
    forge: ForgeRuntime = Depends(get_forge),
) -> dict:
    """Stores the message and starts a turn for the worker it addresses (one turn per group at a time)."""
    try:
        message = await forge.coordinator.post_user_message(account.id, group_id, body.text)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    except GroupBusy as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "A worker is still answering. Wait for it or stop it.") from error
    return message_event(message)


@router.get("/groups/{group_id}/events")
async def group_events(
    request: Request,
    group_id: int,
    after: int = Query(default=0, ge=0),
    groups: GroupService = Depends(get_groups),
    forge: ForgeRuntime = Depends(get_forge),
) -> StreamingResponse:
    """Server-Sent Events: stored messages after `after`, the turn state, then live events
    (message / delta / turn). A message event carries `id: <seq>` so the browser can resume."""
    last_event_id = request.headers.get("last-event-id", "")
    if last_event_id.isdigit():
        after = max(after, int(last_event_id))
    try:
        await groups.get(group_id)
    except GroupNotFound as error:
        raise _not_found("Group") from error

    async def stream() -> AsyncIterator[bytes]:
        async for event in forge.streamer.stream(group_id, after):
            yield sse_frame(event)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/groups/{group_id}/permissions/{request_id}")
async def answer_permission(
    group_id: int,
    request_id: str,
    body: PermissionAnswer,
    account: Account = Depends(require_forge),
    forge: ForgeRuntime = Depends(get_forge),
) -> dict[str, bool]:
    try:
        answered = await forge.coordinator.resolve_permission(account.id, group_id, request_id, body.allow)
    except GroupNotFound as error:
        raise _not_found("Group") from error
    if not answered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing is waiting for that answer")
    return {"answered": True}


@router.post("/groups/{group_id}/cancel")
async def cancel_turn(
    group_id: int,
    account: Account = Depends(require_forge),
    forge: ForgeRuntime = Depends(get_forge),
) -> dict[str, bool]:
    try:
        return {"stopping": await forge.coordinator.cancel(account.id, group_id)}
    except GroupNotFound as error:
        raise _not_found("Group") from error


# --- the worker socket ------------------------------------------------------------------


def _bearer(header: str | None) -> str | None:
    if header and header[:7].lower() == "bearer ":
        return header[7:].strip() or None
    return None


@router.websocket("/worker")
async def worker_socket(websocket: WebSocket) -> None:
    """A worker connects out with its pairing token, says hello (with its plan), then trades
    frames with the coordinator until it disconnects."""
    forge: ForgeRuntime = websocket.app.state.forge
    database = websocket.app.state.database
    token = _bearer(websocket.headers.get("authorization"))
    worker = None
    if token:
        async with database.sessions() as session:
            worker = await WorkerAuthenticator(session).authenticate(token)
    if worker is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        hello = parse_worker_frame(await asyncio.wait_for(websocket.receive_text(), HELLO_TIMEOUT_SECONDS))
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close(code=4400)
        return
    if not isinstance(hello, Hello):
        await websocket.close(code=4400)
        return

    connection = WorkerConnection(worker.id, websocket)
    replaced = forge.registry.register(connection)
    if replaced is not None:
        await replaced.close(4000)
    try:
        async with database.sessions() as session:
            await WorkerAuthenticator(session).record_hello(worker.id, hello.plan)
        await connection.send(ready_frame(worker.id))
        while True:
            frame = parse_worker_frame(await websocket.receive_text())
            if frame is None:
                continue
            if isinstance(frame, Heartbeat):
                async with database.sessions() as session:
                    await WorkerAuthenticator(session).touch(worker.id)
                continue
            await forge.coordinator.on_worker_frame(worker.id, frame)
    except (WebSocketDisconnect, RuntimeError, KeyError):
        pass
    finally:
        forge.registry.drop(worker.id, connection)
        await forge.coordinator.on_worker_disconnected(worker.id)
