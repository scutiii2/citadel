"""/api/triage: typed questions asked straight to the Triage Assistant (Laya), without the orchestrator.

Portcullis checks the login and chat.use; Stronghold (`apps/stronghold/src/triage`) checks the token
limits, asks the agents, records the usage and answers. Option titles come from the title-writer agent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/triage", tags=["triage"])

require_chat = require_permission(CHAT_USE)


@router.post("/titles")
async def write_titles(request: Request, account: Account = Depends(require_chat),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/triage/titles")


@router.post("/ask")
async def ask(request: Request, account: Account = Depends(require_chat),
              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/triage/ask")
