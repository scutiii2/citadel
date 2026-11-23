"""/internal: what Stronghold asks Portcullis for. Never for browsers.

Stronghold asks here for accounts, permissions, logs and requester renewal.
Mandatory service middleware admits only signed Stronghold assertions.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db_session, get_log_writer
from src.models import Account
from src.services.log_service import LogWriter
from src.services.service_auth import identity_headers


router = APIRouter(prefix="/internal", tags=["internal"])
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
_USERNAME = re.compile(r"[A-Za-z0-9_.-]{3,80}")


def _is_usable(account: Account | None) -> bool:
    return account is not None and account.is_active and account.email_verified


@router.get("/accounts/by-username/{username}")
async def account_by_username(
    username: str, session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Resolve a usable recipient with the same username comparison as sign-in."""
    if _USERNAME.fullmatch(username) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipient")
    try:
        account = await session.scalar(select(Account).where(Account.username == username))
    except SQLAlchemyError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Storage is unavailable") from None
    if account is None or not _is_usable(account):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipient")
    return {"uid": account.uid, "username": account.username}


async def _usable_account(session: AsyncSession, uid: str) -> Account:
    """An account that may be contacted: active and verified."""
    account = await session.scalar(select(Account).where(Account.uid == uid))
    if account is None or not _is_usable(account):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipient")
    return account


@router.get("/accounts/{uid}/permissions")
async def permissions(
    uid: Uid, session: AsyncSession = Depends(get_db_session),
) -> dict[str, list[str]]:
    """What a usable account may do right now; 404 for an unknown, inactive or unverified one."""
    account = await _usable_account(session, uid)
    return {"permissions": sorted(account.permission_names)}


class ActionIn(BaseModel):
    action: str = Field(pattern=r"^[a-z0-9_.]{1,60}$")
    message: str = Field(min_length=1, max_length=300)


@router.post("/accounts/{uid}/actions", status_code=status.HTTP_204_NO_CONTENT)
async def log_action(
    uid: Uid, body: ActionIn,
    session: AsyncSession = Depends(get_db_session), logs: LogWriter = Depends(get_log_writer),
) -> Response:
    """Something the account did in Stronghold, for the Logs page. 404 for an unknown account."""
    account = await session.scalar(select(Account).where(Account.uid == uid))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such account")
    await logs.action(account, body.action, body.message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ErrorIn(BaseModel):
    source: str = Field(pattern=r"^[a-z0-9_.]{1,40}$")
    message: str = Field(min_length=1, max_length=500)


@router.post("/errors", status_code=status.HTTP_204_NO_CONTENT)
async def report_error(body: ErrorIn, logs: LogWriter = Depends(get_log_writer)) -> Response:
    """One line in the administrators' Errors log, marked as coming from Stronghold."""
    await logs.error(None, f"stronghold.{body.source}", body.message)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class LogIn(BaseModel):
    kind: Literal["error", "chat_trace"]
    uid: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    source: str = Field(pattern=r"^[a-z0-9_.]{1,40}$")
    message: str = Field(min_length=1, max_length=2000)
    details: str | None = Field(default=None, max_length=100_000)
    # The prompts of a chat trace: JSON text, bounded by the sender (only some admins may read it).
    prompts: str | None = Field(default=None, max_length=500_000)


@router.post("/logs", status_code=status.HTTP_204_NO_CONTENT)
async def write_log(
    body: LogIn, session: AsyncSession = Depends(get_db_session), logs: LogWriter = Depends(get_log_writer),
) -> Response:
    """An account's error or chat-trace line from a chat turn Stronghold ran. Kept under the source name the
    admin Logs pages already know (chat.answer, chat.turn). 404 for an unknown account."""
    account = await session.scalar(select(Account).where(Account.uid == body.uid))
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such account")
    await logs.write(body.kind, account.id, body.source, body.message, body.details, body.prompts)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

class RequesterTokenIn(BaseModel):
    uid: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


@router.post("/requester-token")
async def renew_requester(body: RequesterTokenIn, request: Request,
                          session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    """Renew only active accounts with an existing running Stronghold turn."""
    account = await _usable_account(session, body.uid)
    response = await request.app.state.stronghold.forward("GET", "/turns/running", account)
    import json
    try:
        running = json.loads(response.body)
    except (ValueError, TypeError):
        running = None
    if response.status != 200 or not isinstance(running, dict) or not running.get("chat_ids"):
        raise HTTPException(status.HTTP_409_CONFLICT, "No running turn")
    headers = identity_headers(account.username, account.email, account.uid, fresh=True,
                               identity=request.app.state.keyring)
    return {"token": headers["X-Citadel-Requester"]}

