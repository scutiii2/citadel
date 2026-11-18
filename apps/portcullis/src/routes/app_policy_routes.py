"""/api/admin/app-config: Portcullis's policy settings (session length, new-account role, email verification, login rate
limit, IP filter, security headers, fingerprinting, backups). Needs settings.manage. Saved in Portcullis's settings
database and used from its next start."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.deps import get_log_writer, get_settings, require_permission
from src.config import Settings
from src.models import Account
from src.services import app_policy
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE

router = APIRouter(prefix="/api/admin", tags=["app-config"])
require_manage = require_permission(SETTINGS_MANAGE)


def _path(request: Request):
    return request.app.state.settings_db  # settings.db beside the database


@router.get("/app-config")
async def app_config(request: Request, account: Account = Depends(require_manage),
                     settings: Settings = Depends(get_settings)) -> Any:
    return app_policy.view(settings, _path(request))


@router.put("/app-config")
async def set_app_config(
    changes: dict[str, Any], request: Request, account: Account = Depends(require_manage),
    settings: Settings = Depends(get_settings), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    try:
        changed = app_policy.update(_path(request), settings, changes)
    except app_policy.PolicyError as error:
        raise HTTPException(400, str(error)) from error
    await logs.action(account, "settings.app_config", f"Changed Portcullis settings ({', '.join(changed)})")
    return {**app_policy.view(settings, _path(request)), "applies": "next start"}
