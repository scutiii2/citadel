"""/brain/proposals: the user's door to what agents suggest for long-term memory. Portcullis serves it as /api/brain/proposals.
Only a signed-in person reaches it; the agent's only way in is the MCP tool, which can only create a pending suggestion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel, Field

from src.brain.files_routes import BrainRoute
from src.brain.proposals import BrainProposals
from src.requester import Requester, current_requester

router = APIRouter(prefix="/brain/proposals", tags=["brain-proposals"], route_class=BrainRoute)
ProposalId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


class Landing(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    folder: str | None = Field(default=None, max_length=130)
    remove_items: bool = False


def proposals_of(request: Request) -> BrainProposals:
    return request.app.state.brain_proposals


@router.get("")
async def pending(request: Request, who: Requester = Depends(current_requester)):
    return {"proposals": await proposals_of(request).pending(who.uid)}


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(request: Request, uid: Uid) -> Response:
    await proposals_of(request).purge(uid)
    return Response(status_code=204)


@router.get("/{proposal_id}")
async def one(proposal_id: ProposalId, request: Request, who: Requester = Depends(current_requester)):
    return await proposals_of(request).get(who.uid, proposal_id)


@router.post("/{proposal_id}/accept")
async def accept(proposal_id: ProposalId, request: Request, body: Landing | None = None, who: Requester = Depends(current_requester)):
    given = body or Landing()
    done = await proposals_of(request).accept(who.uid, proposal_id, given.title, given.folder, given.remove_items)
    # The action only, never the title or text.
    await request.app.state.platform.log_action(who.uid, "brain.proposal_accept", "Kept a suggestion")
    return done


@router.post("/{proposal_id}/decline")
async def decline(proposal_id: ProposalId, request: Request, who: Requester = Depends(current_requester)):
    done = await proposals_of(request).decline(who.uid, proposal_id)
    await request.app.state.platform.log_action(who.uid, "brain.proposal_decline", "Declined a suggestion")
    return done
