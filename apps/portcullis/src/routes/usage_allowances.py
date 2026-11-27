"""/api/admin/usage-allowances: free usage resets, cleared usage and limit boosts for accounts (settings.manage).

Staff name accounts by id, or all enabled accounts; Stronghold only ever hears uids.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db_session, get_log_writer, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import as_response
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable

router = APIRouter(prefix="/api/admin/usage-allowances", tags=["usage-allowances"])
require_manage = require_permission(SETTINGS_MANAGE)
GROUP = 500  # Stronghold's cap per request

AccountPath = Annotated[int, Path(gt=0)]
ItemPath = Annotated[str, Path(pattern=r"^[rb]_[A-Za-z0-9]{1,40}$")]
WindowName = Literal["six_hour", "weekly"]
WORDS = {"six_hour": "6-hour", "weekly": "weekly", "both": "6-hour and weekly"}


class Recipients(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: bool = False
    account_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def one_way(self):
        if self.all == bool(self.account_ids):
            raise ValueError("Send all, or account_ids.")
        return self


class GrantBody(Recipients):
    kind: Literal["six_hour", "weekly", "both"]
    count: int = Field(ge=1, le=20)
    expires_at: datetime | None = None


class ClearBody(Recipients):
    windows: list[WindowName] = Field(min_length=1, max_length=2)


class BoostBody(ClearBody):
    percent: int = Field(ge=1, le=1000)
    ends_at: datetime


async def _recipients(session: AsyncSession, body: Recipients) -> dict[str, str]:
    """uid -> username of the accounts meant. Nothing is sent when one is unknown."""
    query = select(Account)
    query = query.where(Account.is_active.is_(True)) if body.all else query.where(Account.id.in_(body.account_ids))
    accounts = list(await session.scalars(query))
    if not body.all and len(accounts) != len(set(body.account_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "An account does not exist.")
    return {account.uid: account.username for account in accounts}


async def _apply(path: str, body: Recipients, summary: str, admin: Account, session: AsyncSession,
                 stronghold: StrongholdForwarder, logs: LogWriter) -> Any:
    names = await _recipients(session, body)
    fields = body.model_dump(mode="json", exclude={"all", "account_ids"}, exclude_none=True)
    uids, done, failed = list(names), 0, []
    for start in range(0, len(uids), GROUP):
        try:
            answer = await stronghold.forward("POST", f"/admin/usage-allowances/{path}", admin,
                                              json={"uids": uids[start:start + GROUP], **fields})
        except StrongholdUnavailable:
            if start == 0:
                raise
            answer = None
        if answer is None or answer.status != 200:
            if start == 0:
                return as_response(answer)  # nothing was changed: pass Stronghold's own refusal on
            failed += uids[start:]
            break
        result = json.loads(answer.body)
        done += result["done"]
        failed += result["failed"]
    everyone = " (all users)" if body.all else ""
    await logs.action(admin, "usage.allowances", f"{summary} for {done} account(s){everyone}")
    return {"done": done, "failed": sorted(names[uid] for uid in failed)}


@router.get("")
async def allowances(admin: Account = Depends(require_manage), session: AsyncSession = Depends(get_db_session),
                     stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Any:
    answer = await stronghold.forward("GET", "/admin/usage-allowances", admin)
    if answer.status != 200:
        return as_response(answer)
    accounts = {account.uid: account for account in await session.scalars(select(Account))}
    rows = [
        {"account_id": accounts[e["uid"]].id, "username": accounts[e["uid"]].username,
         **{key: e[key] for key in ("auto_use", "resets", "boosts")}}
        for e in json.loads(answer.body) if e["uid"] in accounts
    ]
    return sorted(rows, key=lambda row: row["username"].lower())


@router.post("/resets")
async def send_resets(body: GrantBody, admin: Account = Depends(require_manage),
                      session: AsyncSession = Depends(get_db_session),
                      stronghold: StrongholdForwarder = Depends(get_stronghold),
                      logs: LogWriter = Depends(get_log_writer)) -> Any:
    until = f", expiring {body.expires_at.isoformat()}" if body.expires_at else ""
    summary = f"Sent {body.count} free {WORDS[body.kind]} reset(s){until}"
    return await _apply("resets", body, summary, admin, session, stronghold, logs)


@router.post("/clear")
async def clear_usage(body: ClearBody, admin: Account = Depends(require_manage),
                      session: AsyncSession = Depends(get_db_session),
                      stronghold: StrongholdForwarder = Depends(get_stronghold),
                      logs: LogWriter = Depends(get_log_writer)) -> Any:
    summary = f"Reset {' and '.join(WORDS[w] for w in body.windows)} usage"
    return await _apply("clear", body, summary, admin, session, stronghold, logs)


@router.post("/boosts")
async def boost_limits(body: BoostBody, admin: Account = Depends(require_manage),
                       session: AsyncSession = Depends(get_db_session),
                       stronghold: StrongholdForwarder = Depends(get_stronghold),
                       logs: LogWriter = Depends(get_log_writer)) -> Any:
    windows = " and ".join(WORDS[w] for w in body.windows)
    summary = f"Boosted {windows} limits by {body.percent}% until {body.ends_at.isoformat()}"
    return await _apply("boosts", body, summary, admin, session, stronghold, logs)


async def _remove(kind: str, account_id: int, item_id: str, admin: Account, session: AsyncSession,
                  stronghold: StrongholdForwarder, logs: LogWriter) -> Response:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    answer = await stronghold.forward("DELETE", f"/admin/usage-allowances/{account.uid}/{kind}/{item_id}", admin)
    if answer.status < 300:
        what = "an unused reset" if kind == "resets" else "a limit boost"
        await logs.action(admin, "usage.allowances", f"Removed {what} of '{account.username}'")
    return as_response(answer)


@router.delete("/{account_id}/resets/{item_id}")
async def remove_reset(account_id: AccountPath, item_id: ItemPath, admin: Account = Depends(require_manage),
                       session: AsyncSession = Depends(get_db_session),
                       stronghold: StrongholdForwarder = Depends(get_stronghold),
                       logs: LogWriter = Depends(get_log_writer)) -> Response:
    return await _remove("resets", account_id, item_id, admin, session, stronghold, logs)


@router.delete("/{account_id}/boosts/{item_id}")
async def remove_boost(account_id: AccountPath, item_id: ItemPath, admin: Account = Depends(require_manage),
                       session: AsyncSession = Depends(get_db_session),
                       stronghold: StrongholdForwarder = Depends(get_stronghold),
                       logs: LogWriter = Depends(get_log_writer)) -> Response:
    return await _remove("boosts", account_id, item_id, admin, session, stronghold, logs)
