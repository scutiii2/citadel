"""Account-deletion purge for legacy assistant memory kept by Armory."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from src.memory.client import MemoryClient

router = APIRouter(prefix="/memory", tags=["memory"])


def get_memory(request: Request) -> MemoryClient:
    return request.app.state.memory


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        memory: MemoryClient = Depends(get_memory)) -> Response:
    """Everything a deleted account kept. Portcullis calls it; 502 when Armory did not confirm."""
    if not await memory.purge(uid):
        raise HTTPException(502, "Memory was not purged")
    return Response(status_code=204)
