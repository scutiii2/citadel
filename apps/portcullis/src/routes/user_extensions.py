"""/api/user-extensions: the logged-in account's own MCP servers ("private
extensions", chat.use), answered by Stronghold. Private to the account: another account's slug is 404.
The reply carries each one's live status and tools (Stronghold asks Legion, cached for a minute) and
the NAMES of its headers; a header value is never sent back.

Portcullis checks the permission (chat.use to read, extensions.personal.manage to change), passes
the request on and writes the account log line (never a header value or a query string)."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Path, Request, Response, status

from src.deps import get_log_writer, get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.log_service import LogWriter
from src.services.permissions import CHAT_USE, EXTENSIONS_PERSONAL_MANAGE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/user-extensions", tags=["user-extensions"])

require_chat = require_permission(CHAT_USE)
require_manage = require_permission(EXTENSIONS_PERSONAL_MANAGE)

# The slug rules, as in Stronghold (apps/stronghold/src/extensions/service.py).
MAX_SLUG = 40
SLUG_PATTERN = r"^[a-z0-9]+(_[a-z0-9]+)*$"


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _json(raw: bytes | str) -> dict:
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@router.get("")
async def list_extensions(request: Request, account: Account = Depends(require_chat),
                          stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/user-extensions")


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_manage)])
async def add_extension(request: Request, account: Account = Depends(require_chat),
                        stronghold: StrongholdForwarder = Depends(get_stronghold),
                        logs: LogWriter = Depends(get_log_writer)) -> Response:
    """Saves the extension (even if it cannot be reached right now) and probes it once."""
    answer = await pass_on(request, stronghold, account, "/user-extensions")
    if answer.status_code == status.HTTP_201_CREATED:
        saved = _json(answer.body)
        await logs.action(account, "account.user_extension_add",
                          f"Added private extension '{saved.get('label', '')}' ({_host(str(saved.get('url', '')))})")
    return answer


@router.patch("/{slug}", dependencies=[Depends(require_manage)])
async def update_extension(request: Request, slug: str = Path(pattern=SLUG_PATTERN, max_length=MAX_SLUG),
                           account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold),
                           logs: LogWriter = Depends(get_log_writer)) -> Response:
    answer = await pass_on(request, stronghold, account, f"/user-extensions/{slug}")
    if answer.status_code == status.HTTP_200_OK:
        asked = _json(await request.body())
        saved = _json(answer.body)
        label = saved.get("label", "")
        if set(asked) == {"enabled"} and asked["enabled"] is not None:
            message = f"{'Enabled' if asked['enabled'] else 'Disabled'} private extension '{label}'"
        else:
            message = f"Edited private extension '{label}' ({_host(str(saved.get('url', '')))})"
        await logs.action(account, "account.user_extension_edit", message)
    return answer


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_manage)])
async def remove_extension(request: Request, slug: str = Path(pattern=SLUG_PATTERN, max_length=MAX_SLUG),
                           account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold),
                           logs: LogWriter = Depends(get_log_writer)) -> Response:
    answer = await pass_on(request, stronghold, account, f"/user-extensions/{slug}")
    if answer.status_code == status.HTTP_204_NO_CONTENT:
        await logs.action(account, "account.user_extension_remove", f"Removed private extension '{slug}'")
    return answer
