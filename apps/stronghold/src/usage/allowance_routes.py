"""/admin/usage-allowances: free resets, cleared usage and limit boosts for accounts. Portcullis serves them to
staff as /api/admin/usage-allowances (settings.manage) and names the accounts by uid."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field

from src.document_store import DbGatewayError
from src.usage.allowance import AllowanceError
from src.usage.routes import get_usage
from src.usage.service import UsageService, utcnow

router = APIRouter(prefix="/admin/usage-allowances", tags=["usage-allowances"])

Uid = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
UidPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ItemPath = Annotated[str, Path(pattern=r"^[rb]_[A-Za-z0-9]{1,40}$")]
WindowName = Literal["six_hour", "weekly"]


class Recipients(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uids: list[Uid] = Field(min_length=1, max_length=500)


class GrantBody(Recipients):
    kind: Literal["six_hour", "weekly", "both"]
    count: int = Field(ge=1, le=20)
    expires_at: datetime | None = None


class ClearBody(Recipients):
    windows: list[WindowName] = Field(min_length=1, max_length=2)


class BoostBody(ClearBody):
    percent: int = Field(ge=1, le=1000)
    ends_at: datetime


def _future(value: datetime, name: str) -> datetime:
    """`value` as naive UTC, refused unless it is still to come."""
    at = value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
    if at <= utcnow():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{name} must be in the future")
    return at


async def _each(uids: list[str], apply: Callable[[str], Awaitable[None]]) -> dict[str, Any]:
    """`apply` to every account; one that fails does not stop the others."""
    done, failed = 0, []
    for uid in dict.fromkeys(uids):
        try:
            await apply(uid)
            done += 1
        except (AllowanceError, DbGatewayError):
            failed.append(uid)
    return {"done": done, "failed": failed}


@router.get("")
async def allowances(usage: UsageService = Depends(get_usage)) -> list[dict[str, Any]]:
    return await usage.allowance_list()


@router.post("/resets")
async def send_resets(body: GrantBody, usage: UsageService = Depends(get_usage)) -> dict[str, Any]:
    expires = _future(body.expires_at, "expires_at") if body.expires_at else None
    return await _each(body.uids, lambda uid: usage.grant(uid, body.kind, body.count, expires))


@router.post("/clear")
async def clear_usage(body: ClearBody, usage: UsageService = Depends(get_usage)) -> dict[str, Any]:
    windows = tuple(dict.fromkeys(body.windows))
    return await _each(body.uids, lambda uid: usage.clear(uid, windows))


@router.post("/boosts")
async def boost_limits(body: BoostBody, usage: UsageService = Depends(get_usage)) -> dict[str, Any]:
    ends, windows = _future(body.ends_at, "ends_at"), tuple(dict.fromkeys(body.windows))
    return await _each(body.uids, lambda uid: usage.boost(uid, windows, body.percent, ends))


async def _removed(remove: Awaitable[None]) -> Response:
    try:
        await remove
    except AllowanceError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{uid}/resets/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reset(uid: UidPath, item_id: ItemPath, usage: UsageService = Depends(get_usage)) -> Response:
    return await _removed(usage.remove_reset(uid, item_id))


@router.delete("/{uid}/boosts/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_boost(uid: UidPath, item_id: ItemPath, usage: UsageService = Depends(get_usage)) -> Response:
    return await _removed(usage.remove_boost(uid, item_id))
