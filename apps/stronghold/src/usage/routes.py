"""/usage: an account's token usage and limits, kept in Treasury.

Portcullis serves the reads as /api/usage (chat.use) and /api/admin/usage (usage.all.view), and
calls /usage/check and POST /usage/records for every chat turn, triage question and other agent call.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from src.clock import utcnow
from src.requester import Requester, current_requester
from src.usage.allowance import NothingToReset, ResetNotFound
from src.usage.service import MAX_REPORT_DAYS, UsageService

router = APIRouter(prefix="/usage", tags=["usage"])

Days = Annotated[int, Query(ge=1, le=MAX_REPORT_DAYS)]
Since = Annotated[date | None, Query()]
Agent = Annotated[str | None, Query(max_length=120)]
Provider = Annotated[str | None, Query(max_length=60)]


def get_usage(request: Request) -> UsageService:
    return request.app.state.usage


def check_since(since: date | None) -> date | None:
    """`since` (a UTC day) must not be in the future or older than the longest report."""
    if since is None:
        return None
    today = utcnow().date()
    if since > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "since must not be in the future")
    if today - since > timedelta(days=MAX_REPORT_DAYS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"since must be within the last {MAX_REPORT_DAYS} days")
    return since


class UsageRow(BaseModel):
    """What one agent spent on one call. Portcullis has already read it out of the agent's answer."""

    model_config = ConfigDict(extra="ignore")

    agent: str | None = Field(default=None, max_length=120)
    agent_id: str | None = Field(default=None, max_length=120)
    provider_id: str | None = Field(default=None, max_length=60)
    gateway: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=120)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int = Field(gt=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    delegated_by: str | None = Field(default=None, max_length=120)


class RecordBody(BaseModel):
    turn_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="chat", min_length=1, max_length=20)
    chat_id: str | None = Field(default=None, max_length=64)
    rows: list[UsageRow] = Field(max_length=100)


@router.get("/pricing")
async def pricing(request: Request) -> dict[str, Any]:
    """The model price table (per million tokens). Stronghold owns it; Portcullis reads it to price chat messages."""
    return request.app.state.pricing.document()


@router.post("/check")
async def check(requester: Requester = Depends(current_requester), usage: UsageService = Depends(get_usage)) -> dict[str, Any]:
    """`{"block": null}`, or `{"block": {reason, reset_at}}` when a token limit is reached."""
    block = await usage.check(requester.uid)
    return {"block": asdict(block) if block else None}


class AutoReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


@router.put("/auto-reset")
async def set_auto_reset(body: AutoReset, requester: Requester = Depends(current_requester),
                         usage: UsageService = Depends(get_usage)) -> dict[str, Any]:
    await usage.set_auto_use(requester.uid, body.enabled)
    return await usage.overview(requester.uid)


@router.post("/resets/{reset_id}/use")
async def use_reset(reset_id: Annotated[str, Path(pattern=r"^r_[A-Za-z0-9]{1,40}$")],
                    requester: Requester = Depends(current_requester),
                    usage: UsageService = Depends(get_usage)) -> dict[str, Any]:
    try:
        await usage.use_reset(requester.uid, reset_id)
    except ResetNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except NothingToReset as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return await usage.overview(requester.uid)


@router.post("/records", status_code=status.HTTP_201_CREATED)
async def record(body: RecordBody, requester: Requester = Depends(current_requester),
                 usage: UsageService = Depends(get_usage)) -> dict[str, int]:
    rows = [row.model_dump(mode="json", exclude_none=False) for row in body.rows]
    return {"total": await usage.record(requester.uid, body.turn_id, body.kind, body.chat_id, rows)}


@router.get("")
async def my_usage(
    days: Days = 30, since: Since = None, group_by: Literal["agent", "provider", "gateway", "model"] = "agent",
    agent: Agent = None, provider: Provider = None,
    requester: Requester = Depends(current_requester), usage: UsageService = Depends(get_usage),
) -> dict[str, Any]:
    since = check_since(since)
    return {
        **await usage.overview(requester.uid),
        "report": await usage.report(requester.uid, days, since, group_by=group_by, agent=agent, provider=provider),
    }


@router.get("/records")
async def my_usage_records(
    days: Days = 30, since: Since = None, agent: Agent = None, provider: Provider = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    requester: Requester = Depends(current_requester), usage: UsageService = Depends(get_usage),
) -> list[dict[str, Any]]:
    return await usage.records(requester.uid, days, check_since(since), agent=agent, provider=provider, limit=limit)


@router.get("/all")
async def all_usage(days: Days = 30, since: Since = None, usage: UsageService = Depends(get_usage)) -> list[dict[str, Any]]:
    """Totals per account uid, for the administrators' page. Portcullis adds the account names."""
    return await usage.all_accounts(days, check_since(since))


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        usage: UsageService = Depends(get_usage)) -> Response:
    """Every usage row of a deleted account. Portcullis calls it when an administrator deletes the account."""
    await usage.purge_owner(uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
