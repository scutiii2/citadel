"""/internal: what Stronghold asks Portcullis for. Never for browsers.

Stronghold asks here for what Portcullis owns: accounts, permissions and the logs. Every route needs the shared
internal token; with none configured the routes refuse, because Portcullis is the
one service that outside machines can reach.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db_session, get_log_writer, get_settings
from src.config import Settings
from src.models import Account
from src.services.log_service import LogWriter


def require_internal(request: Request, x_internal_token: str = Header("")) -> None:
    expected: str | None = request.app.state.internal_token
    if not expected or not hmac.compare_digest(expected.encode("utf-8"), x_internal_token.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing internal API token")


router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal)])
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


async def _usable_account(session: AsyncSession, settings: Settings, uid: str) -> Account:
    """An account that may be contacted: active, and verified when verification is required."""
    account = await session.scalar(select(Account).where(Account.uid == uid))
    if account is None or not account.is_active or (settings.require_email_verification and not account.email_verified):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such recipient")
    return account


@router.get("/accounts/{uid}/permissions")
async def permissions(
    uid: Uid, session: AsyncSession = Depends(get_db_session), settings: Settings = Depends(get_settings),
) -> dict[str, list[str]]:
    """What a usable account may do right now; 404 for an unknown, inactive or unverified one."""
    account = await _usable_account(session, settings, uid)
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
