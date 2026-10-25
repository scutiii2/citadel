"""The Laya decision strategy of the Triage Assistant.

/api/admin/triage-strategy: the default for everyone, kept by Garrison (llm/triage_strategy.py); needs
settings.manage. /api/account/triage-strategy: the logged-in account's own choice (accounts.triage_strategy);
null follows the default. Strategy names are the Laya service's own list, read through Garrison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import current_account, get_db_session, get_log_writer, require_permission
from src.models import Account
from src.routes.agent_admin import get_agent_admin
from src.services.agent_admin import AgentAdmin, AgentAdminRefused, AgentAdminUnavailable
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE

admin_router = APIRouter(prefix="/api/admin/triage-strategy", tags=["triage-strategy"])
account_router = APIRouter(prefix="/api/account/triage-strategy", tags=["triage-strategy"])

require_settings_manage = require_permission(SETTINGS_MANAGE)


class StrategyIn(BaseModel):
    # Required (no default): null clears, a missing field is a 422.
    value: str | None


async def _garrison(awaitable) -> Any:
    try:
        return await awaitable
    except AgentAdminUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "ai_agent is unreachable") from error
    except AgentAdminRefused as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error


@admin_router.get("")
async def read_default(
    account: Account = Depends(require_settings_manage), admin: AgentAdmin = Depends(get_agent_admin)
) -> dict[str, Any]:
    return await _garrison(admin.triage_strategy(account))


@admin_router.put("")
async def set_default(
    body: StrategyIn,
    account: Account = Depends(require_settings_manage),
    admin: AgentAdmin = Depends(get_agent_admin),
    logs: LogWriter = Depends(get_log_writer),
) -> dict[str, Any]:
    before = (await _garrison(admin.triage_strategy(account))).get("default")
    after = await _garrison(admin.set_triage_strategy(account, body.value))
    await logs.action(account, "triage_strategy.default", f"Default triage strategy: {before or 'not set'} -> {after.get('default') or 'not set'}")
    return after


@account_router.get("")
async def read_own(account: Account = Depends(current_account), admin: AgentAdmin = Depends(get_agent_admin)) -> dict[str, Any]:
    """The account's value, the default it falls back to and the strategies on offer (empty while Garrison is unreachable)."""
    try:
        info = await admin.triage_strategy(account)
    except (AgentAdminUnavailable, AgentAdminRefused):
        info = {"default": None, "strategies": []}
    return {"value": account.triage_strategy, "default": info.get("default"), "strategies": info.get("strategies", [])}


@account_router.put("")
async def set_own(
    body: StrategyIn,
    account: Account = Depends(current_account),
    admin: AgentAdmin = Depends(get_agent_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if body.value is not None:
        try:
            info = await admin.triage_strategy(account)
        except (AgentAdminUnavailable, AgentAdminRefused) as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The strategy list is unavailable; try again later") from error
        names = info.get("strategies", [])
        if not names:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The strategy list is unavailable; try again later")
        if body.value not in names:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown strategy; choose one of: {', '.join(names)}")
    else:
        info = {"default": None, "strategies": []}
    if account.triage_strategy != body.value:
        account.triage_strategy = body.value
        await session.commit()
    if body.value is None:
        try:
            info = await admin.triage_strategy(account)
        except (AgentAdminUnavailable, AgentAdminRefused):
            pass
    return {"value": account.triage_strategy, "default": info.get("default"), "strategies": info.get("strategies", [])}
