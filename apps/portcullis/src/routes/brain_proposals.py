"""/api/brain/proposals: what agents suggest for long-term memory, answered by Stronghold.
Only a signed-in session reaches it (chat.use). Outside clients must never be given these routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold
from src.models import Account
from src.routes.chats import require_chat
from src.routes.stronghold import pass_on
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/brain/proposals", tags=["brain-proposals"])
Hex = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


@router.get("")
async def list_proposals(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/proposals")


@router.get("/{proposal_id}")
async def read_proposal(
    proposal_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/proposals/{proposal_id}")


@router.post("/{proposal_id}/accept")
async def accept_proposal(
    proposal_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/proposals/{proposal_id}/accept")


@router.post("/{proposal_id}/decline")
async def decline_proposal(
    proposal_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/proposals/{proposal_id}/decline")
