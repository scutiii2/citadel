"""/tuning: the logged-in account's own response limits (lower only).

Portcullis serves these as /api/account/tuning (any login) and reads /tuning/limits/own when a chat
turn starts. The administrator's tuning of Legion itself stays at /api/admin/tuning.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field

from src.document_store import DbGatewayUnavailable
from src.requester import Requester, current_requester
from src.tuning.limits import FIELDS, LegionTuning, LegionUnavailable, LimitsStore

router = APIRouter(prefix="/tuning", tags=["tuning"])


def get_limits(request: Request) -> LimitsStore:
    return request.app.state.limits


def get_legion(request: Request) -> LegionTuning:
    return request.app.state.legion


class LimitsBody(BaseModel):
    max_output_tokens: int | None = Field(default=None, ge=1, le=200_000)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=100)


class LimitsOut(BaseModel):
    limits: LimitsBody
    ceiling: LimitsBody


async def _ceiling(legion: LegionTuning, who: Requester) -> LimitsBody:
    """The admin's current values; empty when Legion is unreachable."""
    try:
        default = await legion.ceiling(who)
    except LegionUnavailable:
        return LimitsBody()
    return LimitsBody(**{f: default.get(f) for f in FIELDS})


@router.get("/limits")
async def read_limits(who: Requester = Depends(current_requester), limits: LimitsStore = Depends(get_limits),
                      legion: LegionTuning = Depends(get_legion)) -> LimitsOut:
    try:
        stored = await limits.get(who.uid)
    except DbGatewayUnavailable:
        stored = {}
    return LimitsOut(limits=LimitsBody(**stored), ceiling=await _ceiling(legion, who))


@router.get("/limits/own")
async def own_limits(who: Requester = Depends(current_requester), limits: LimitsStore = Depends(get_limits)) -> dict[str, int]:
    """Only the account's stored values: what a chat turn starts with. Storage trouble means none."""
    try:
        return await limits.get(who.uid)
    except DbGatewayUnavailable:
        return {}


@router.put("/limits")
async def save_limits(body: LimitsBody, who: Requester = Depends(current_requester),
                      limits: LimitsStore = Depends(get_limits), legion: LegionTuning = Depends(get_legion)) -> LimitsOut:
    """Saves both values (null clears one). Refused while Legion is unreachable, because
    the admin's current value is the cap."""
    try:
        admin_values = await legion.ceiling(who)
    except LegionUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The agents are unreachable, so limits cannot be checked") from error
    for field in FIELDS:
        value, cap = getattr(body, field), admin_values.get(field)
        if value is not None and isinstance(cap, int) and value > cap:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} cannot be above {cap}")
    try:
        stored = await limits.replace(who.uid, body.model_dump())
    except DbGatewayUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Limits storage is unavailable") from error
    return LimitsOut(limits=LimitsBody(**stored), ceiling=LimitsBody(**{f: admin_values.get(f) for f in FIELDS}))


@router.delete("/limits", status_code=status.HTTP_204_NO_CONTENT)
async def reset_limits(who: Requester = Depends(current_requester), limits: LimitsStore = Depends(get_limits)) -> Response:
    try:
        await limits.reset(who.uid)
    except DbGatewayUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Limits storage is unavailable") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        limits: LimitsStore = Depends(get_limits)) -> Response:
    """A deleted account's limits. Portcullis calls it when an administrator deletes the account."""
    await limits.reset(uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
