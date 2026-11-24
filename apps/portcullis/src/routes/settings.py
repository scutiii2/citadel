"""/api/settings: what the administrator has switched on for everyone.

Read-only for any logged-in account (the browser shows what is required of
it); tool approval is Armory's rule and is changed under /api/armory-tool-approval. /api/settings/pages
lists the pages hidden from every account's sidebar."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.deps import current_account, get_settings_service
from src.models import Account
from src.routes.server_info import get_server_info
from src.services.mcp_server_info import McpServerInfo
from src.services.tool_approval import forced_approval
from src.services.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def read_settings(
    account: Account = Depends(current_account),
    info: McpServerInfo = Depends(get_server_info),
    app_settings: SettingsService = Depends(get_settings_service),
) -> dict[str, bool]:
    """What the administrator requires of everyone. Armory owns the rule; this only relays it."""
    return {"force_tool_approval": await forced_approval(info, app_settings, account)}


class HiddenPagesOut(BaseModel):
    hidden: list[str]


@router.get("/pages")
async def read_hidden_pages(
    _account: Account = Depends(current_account),
    app_settings: SettingsService = Depends(get_settings_service),
) -> HiddenPagesOut:
    return HiddenPagesOut(hidden=await app_settings.hidden_pages())
