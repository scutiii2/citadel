# apps/Ember/ember_api/src/routes/account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits (lower only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.deps import current_account, get_db_gateway
from src.models import Account
from src.routes.agent_admin import get_agent_admin
from src.services.agent_admin import AgentAdmin, AgentAdminRefused, AgentAdminUnavailable
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.tuning_limits_service import FIELDS, TuningLimitsService

router = APIRouter(prefix="/api/account/tuning", tags=["account-tuning"])


def get_limits_service(
    account: Account = Depends(current_account), store: DocumentStore = Depends(get_db_gateway)
) -> TuningLimitsService:
    return TuningLimitsService(store, account.uid)


class LimitsBody(BaseModel):
    max_output_tokens: int | None = Field(default=None, ge=1, le=200_000)
    max_tool_rounds: int | None = Field(default=None, ge=1, le=100)


class LimitsOut(BaseModel):
    limits: LimitsBody
    ceiling: LimitsBody


async def _ceiling(admin: AgentAdmin, account: Account) -> LimitsBody:
    """The admin's current values (what the user's own can not exceed); empty when legion is unreachable."""
    try:
        default = (await admin.tuning(account))["effective"]["token_limits"]["default"]
    except (AgentAdminUnavailable, AgentAdminRefused, KeyError, TypeError):
        return LimitsBody()
    return LimitsBody(**{f: default.get(f) for f in FIELDS})


@router.get("")
async def read_limits(
    account: Account = Depends(current_account),
    service: TuningLimitsService = Depends(get_limits_service),
    admin: AgentAdmin = Depends(get_agent_admin),
) -> LimitsOut:
    try:
        stored = await service.get()
    except DbGatewayError:
        stored = {}
    return LimitsOut(limits=LimitsBody(**stored), ceiling=await _ceiling(admin, account))


@router.put("")
async def save_limits(
    body: LimitsBody,
    account: Account = Depends(current_account),
    service: TuningLimitsService = Depends(get_limits_service),
    admin: AgentAdmin = Depends(get_agent_admin),
) -> LimitsOut:
    """Saves both values (null clears one). Refused while legion is unreachable, because
    the admin's current value is the cap."""
    try:
        admin_values = (await admin.tuning(account))["effective"]["token_limits"]["default"]
    except (AgentAdminUnavailable, AgentAdminRefused, KeyError, TypeError) as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The agents are unreachable, so limits cannot be checked") from error
    for field in FIELDS:
        value, cap = getattr(body, field), admin_values.get(field)
        if value is not None and isinstance(cap, int) and value > cap:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} cannot be above {cap}")
    try:
        stored = await service.replace(body.model_dump())
    except DbGatewayError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Limits storage is unavailable") from error
    return LimitsOut(limits=LimitsBody(**stored), ceiling=LimitsBody(**{f: admin_values.get(f) for f in FIELDS}))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_limits(service: TuningLimitsService = Depends(get_limits_service)) -> Response:
    try:
        await service.reset()
    except DbGatewayError as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Limits storage is unavailable") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
