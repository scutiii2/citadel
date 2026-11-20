"""/api/admin/stronghold-brain-settings: Stronghold's brain limits. Needs settings.manage.
Stronghold validates and keeps them in its settings database and uses a change at once."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from src.deps import get_log_writer, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/admin", tags=["brain-settings"])
require_manage = require_permission(SETTINGS_MANAGE)


@router.get("/stronghold-brain-settings")
async def brain_settings(request: Request, account: Account = Depends(require_manage),
                         stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/brain-settings")


@router.put("/stronghold-brain-settings")
async def set_brain_settings(request: Request, account: Account = Depends(require_manage),
                             stronghold: StrongholdForwarder = Depends(get_stronghold),
                             logs: LogWriter = Depends(get_log_writer)) -> Response:
    answer = await pass_on(request, stronghold, account, "/admin/brain-settings")
    if answer.status_code < 300:
        await logs.action(account, "settings.brain", "Changed Stronghold brain settings")
    return answer
