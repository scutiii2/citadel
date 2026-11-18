"""/api/admin/tool-tokens (Portcullis's own tokens for Bard and Scribe) and /api/admin/stronghold-tool-tokens
(Stronghold's, for Bard, Scribe and Reader). Needs settings.manage. A token is saved in the owning service's settings
database, used by the next request, and never returned or logged."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.deps import get_log_writer, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services import tool_tokens
from src.services.log_service import LogWriter
from src.services.permissions import SETTINGS_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/admin", tags=["tool-tokens"])
require_manage = require_permission(SETTINGS_MANAGE)


def _current(request: Request) -> dict[str, str | None]:
    return {"scribe": request.app.state.scribe_token}


@router.get("/tool-tokens")
async def own_tokens(request: Request, account: Account = Depends(require_manage)) -> Any:
    return tool_tokens.view(request.app.state.tool_tokens_db, _current(request))


@router.put("/tool-tokens")
async def set_own_tokens(
    changes: dict[str, str | None], request: Request,
    account: Account = Depends(require_manage), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    path = request.app.state.tool_tokens_db
    try:
        saved = tool_tokens.update(path, changes)
    except tool_tokens.TokenError as error:
        raise HTTPException(400, str(error)) from error
    for name in saved:
        # A removed token falls back to the environment's one (the starting value), if any.
        setattr(request.app.state, f"{name}_token", tool_tokens.token_for(path, name, request.app.state.env_tool_tokens.get(name)))
    await logs.action(account, "settings.tool_tokens", f"Changed Portcullis tool service tokens ({', '.join(sorted(saved))})")
    return tool_tokens.view(path, _current(request))


@router.get("/stronghold-tool-tokens")
async def stronghold_tokens(request: Request, account: Account = Depends(require_manage),
                            stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/admin/tool-tokens")


@router.put("/stronghold-tool-tokens")
async def set_stronghold_tokens(
    request: Request, account: Account = Depends(require_manage),
    stronghold: StrongholdForwarder = Depends(get_stronghold), logs: LogWriter = Depends(get_log_writer),
) -> Response:
    try:
        names = sorted(await request.json())
    except (ValueError, TypeError):
        names = []
    answer = await pass_on(request, stronghold, account, "/admin/tool-tokens")
    if answer.status_code < 300:
        await logs.action(account, "settings.tool_tokens", f"Changed Stronghold tool service tokens ({', '.join(names)})")
    return answer
