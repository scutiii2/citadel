"""/api/templates: the logged-in account's saved prompts, answered by Stronghold.

Portcullis checks the login and the chat.use permission, then passes the request on.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/templates", tags=["templates"])
require_chat = require_permission(CHAT_USE)

# One segment of 32 hex, so Stronghold's /templates/accounts/<uid> purge route is out of reach from here.
TemplateId = Path(pattern=r"^[0-9a-f]{32}$")


@router.api_route("", methods=["GET", "POST"])
async def templates(request: Request, account: Account = Depends(require_chat),
                    stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/templates")


@router.api_route("/{template_id}", methods=["PUT", "DELETE"])
async def template(request: Request, template_id: str = TemplateId, account: Account = Depends(require_chat),
                   stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/templates/{template_id}")
