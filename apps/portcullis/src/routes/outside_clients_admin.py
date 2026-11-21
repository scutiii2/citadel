"""/api/admin/outside-clients: records, keys and audit events of the outside clients. Needs settings.manage.
A key is returned only by create and rotate-key; logs name the client and the changed fields, never a key."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.models.outside_client import OutsideClient
from src.services.log_service import LogWriter
from src.services.outside_clients import OutsideClientError, OutsideClients
from src.services.permissions import SETTINGS_MANAGE

router = APIRouter(prefix="/api/admin/outside-clients", tags=["outside-clients"])
require_manage = require_permission(SETTINGS_MANAGE)


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    services: list[str] = ["legion"]
    rate_per_minute: int = 10
    budget_tokens: int
    budget_days: int = 30
    ip_allow: list[str] = []


class UpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    services: list[str] | None = None
    ip_allow: list[str] | None = None
    rate_per_minute: int | None = None
    budget_tokens: int | None = None
    budget_days: int | None = None
    enabled: bool | None = None


async def _view(clients: OutsideClients, c: OutsideClient) -> dict[str, Any]:
    used, resets_at = await clients.spent(c)
    return {
        "id": c.id, "uid": c.uid, "name": c.name, "key_prefix": c.key_prefix, "services": c.services,
        "ip_allow": c.ip_allow, "rate_per_minute": c.rate_per_minute, "enabled": c.enabled,
        "created_at": c.created_at, "last_used_at": c.last_used_at,
        "budget": {"tokens": c.budget_tokens, "days": c.budget_days, "used": used,
                   "remaining": max(0, c.budget_tokens - used), "resets_at": resets_at},
    }


async def _found(clients: OutsideClients, client_id: int) -> OutsideClient:
    found = await clients.get(client_id)
    if found is None:
        raise HTTPException(404, "No such client.")
    return found


async def _session(request: Request):
    async with request.app.state.database.sessions() as session:
        yield session


@router.post("", status_code=201)
async def create(body: CreateBody, session=Depends(_session), account: Account = Depends(require_manage),
                 logs: LogWriter = Depends(get_log_writer)) -> Any:
    clients = OutsideClients(session)
    try:
        made, key = await clients.create(**body.model_dump())
    except OutsideClientError as error:
        raise HTTPException(400, str(error)) from error
    await session.commit()
    await logs.action(account, "outside_client.create", f"Created outside client {made.id} ({made.name})")
    return {"client": await _view(clients, made), "key": key}


@router.get("")
async def list_clients(session=Depends(_session), account: Account = Depends(require_manage)) -> Any:
    clients = OutsideClients(session)
    return {"clients": [await _view(clients, c) for c in await clients.list()]}


@router.get("/{client_id}")
async def detail(client_id: int, limit: int = Query(50, ge=1, le=200), before_id: int | None = None,
                 session=Depends(_session), account: Account = Depends(require_manage)) -> Any:
    clients = OutsideClients(session)
    found = await _found(clients, client_id)
    events = await clients.events(client_id, limit, before_id)
    return {**await _view(clients, found), "events": [
        {"id": e.id, "at": e.at, "service": e.service, "action": e.action, "reason": e.reason,
         "status": e.status, "tokens": e.tokens, "ip": e.ip} for e in events]}


@router.patch("/{client_id}")
async def update(client_id: int, body: UpdateBody, session=Depends(_session),
                 account: Account = Depends(require_manage), logs: LogWriter = Depends(get_log_writer)) -> Any:
    clients = OutsideClients(session)
    await _found(clients, client_id)
    changes = body.model_dump(exclude_unset=True)
    try:
        found = await clients.update(client_id, **changes)
    except OutsideClientError as error:
        raise HTTPException(400, str(error)) from error
    await session.commit()
    await logs.action(account, "outside_client.update",
                      f"Changed outside client {found.id} ({found.name}): {', '.join(changes) or 'nothing'}")
    return await _view(clients, found)


@router.post("/{client_id}/rotate-key")
async def rotate(client_id: int, session=Depends(_session), account: Account = Depends(require_manage),
                 logs: LogWriter = Depends(get_log_writer)) -> Any:
    clients = OutsideClients(session)
    await _found(clients, client_id)
    found, key = await clients.rotate_key(client_id)
    await session.commit()
    await logs.action(account, "outside_client.rotate", f"Rotated the key of outside client {found.id} ({found.name})")
    return {"client": await _view(clients, found), "key": key}


@router.delete("/{client_id}", status_code=204)
async def delete(client_id: int, session=Depends(_session), account: Account = Depends(require_manage),
                 logs: LogWriter = Depends(get_log_writer)) -> Response:
    clients = OutsideClients(session)
    found = await _found(clients, client_id)
    label = f"{found.id} ({found.name})"
    await clients.delete(client_id)
    await session.commit()
    await logs.action(account, "outside_client.delete", f"Deleted outside client {label}")
    return Response(status_code=204)
