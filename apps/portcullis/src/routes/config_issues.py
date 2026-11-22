"""/api/config-issues: problems in portcullis's config and secret files
(config.issues.view). File and key names only, never secret values."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.config import Settings
from src.deps import get_settings, get_stronghold, require_permission
from src.models import Account
from src.routes.connections import readiness
from src.services.config_validation import collect_issues_async
from src.services.permissions import CONFIG_ISSUES_VIEW
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/config-issues", tags=["config"])

require_config = require_permission(CONFIG_ISSUES_VIEW)


class ConfigIssueOut(BaseModel):
    file: str
    key: str
    message: str
    severity: Literal["error", "warning"]


@router.get("")
async def list_config_issues(
    account: Account = Depends(require_config), settings: Settings = Depends(get_settings),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> list[ConfigIssueOut]:
    issues = [
        ConfigIssueOut(file=i.file, key=i.key, message=i.message, severity=i.severity)  # type: ignore[arg-type]
        for i in await collect_issues_async(settings)
    ]
    for name, state in (await readiness(stronghold, account)).items():
        if state.reason:
            issues.append(ConfigIssueOut(file="Stronghold Tool services", key=name, message=state.reason, severity="error"))
    return issues
