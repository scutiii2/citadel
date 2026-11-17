"""/api/admin/stronghold-usage-settings: Stronghold's usage limits and price table. Needs settings.manage.
Stronghold validates and keeps them in its settings database and uses a change at once."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from src.deps import get_log_writer, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/admin", tags=["usage-settings"])
require_manage = require_permission(SETTINGS_MANAGE)


@router.get("/stronghold-usage-settings")
async def usage_settings(request: Request, account: Account = Depends(require_manage),
                         stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/usage-settings")


@router.put("/stronghold-usage-settings")
async def set_usage_settings(request: Request, account: Account = Depends(require_manage),
                             stronghold: StrongholdForwarder = Depends(get_stronghold),
                             logs: LogWriter = Depends(get_log_writer)) -> Response:
    try:
        sections = sorted(await request.json())
    except (ValueError, TypeError):
        sections = []
    answer = await pass_on(request, stronghold, account, "/admin/usage-settings")
    if answer.status_code < 300:
        await logs.action(account, "settings.usage", f"Changed Stronghold usage settings ({', '.join(sections)})")
    return answer
