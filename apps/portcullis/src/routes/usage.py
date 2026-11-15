"""/api/usage: the logged-in account's token usage and limits (chat.use),
and /api/admin/usage: every account's totals (usage.all.view). Stronghold keeps the usage."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db_session, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import as_response, pass_on
from src.services.permissions import CHAT_USE, USAGE_ALL_VIEW
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(tags=["usage"])

require_chat = require_permission(CHAT_USE)
require_admin = require_permission(USAGE_ALL_VIEW)


async def get_usage_account(
    account_id: int = Path(gt=0),
    _admin: Account = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> Account:
    """Authorize inspection before looking up even an inactive target account."""
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


@router.get("/api/usage")
async def my_usage(request: Request, account: Account = Depends(require_chat),
                   stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/usage")


@router.get("/api/usage/records")
async def my_usage_records(request: Request, account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/usage/records")


@router.get("/api/admin/usage")
async def all_usage(request: Request, admin: Account = Depends(require_admin),
                    stronghold: StrongholdForwarder = Depends(get_stronghold),
                    session: AsyncSession = Depends(get_db_session)) -> Response:
    """Every account, with the totals Stronghold has for it (zero for an account that used nothing)."""
    answer = await stronghold.forward("GET", "/usage/all", admin, params=dict(request.query_params))
    if answer.status != 200:
        return as_response(answer)
    totals = {entry["uid"]: entry for entry in json.loads(answer.body)}
    accounts = (await session.execute(select(Account))).scalars()
    rows = []
    for account in accounts:
        entry = totals.get(account.uid, {})
        rows.append({"account_id": account.id, "username": account.username, "tokens": entry.get("tokens", 0),
                     "turns": entry.get("turns", 0), "last_used_at": entry.get("last_used_at")})
    rows.sort(key=lambda row: (-row["tokens"], row["username"], row["account_id"]))
    return Response(json.dumps(rows), media_type="application/json")


@router.get("/api/admin/usage/{account_id}")
async def account_usage(request: Request, account: Account = Depends(get_usage_account),
                        stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/usage")


@router.get("/api/admin/usage/{account_id}/records")
async def account_usage_records(request: Request, account: Account = Depends(get_usage_account),
                                stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/usage/records")
