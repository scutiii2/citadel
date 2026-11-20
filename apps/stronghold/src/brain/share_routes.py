"""Account purge for brain shares and blocks."""

from typing import Annotated

from fastapi import APIRouter, Path, Request, Response

from src.brain.files_routes import BrainRoute
from src.brain.shares import BrainShares

router = APIRouter(prefix="/brain/shares", tags=["brain-shares"], route_class=BrainRoute)
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


def shares_of(request: Request) -> BrainShares:
    return request.app.state.brain_shares


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(request: Request, uid: Uid) -> Response:
    await shares_of(request).purge(uid)
    return Response(status_code=204)
