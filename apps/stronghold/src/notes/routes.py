"""Account-deletion purge for legacy notes kept in Treasury."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Path, Request, Response, status

from src.document_store import DbGatewayError, DocumentStore
from src.notes.store import purge_owner

router = APIRouter(prefix="/notes", tags=["notes"])


def _fail(error: DbGatewayError) -> NoReturn:
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Notes storage is unavailable") from error


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")], request: Request) -> Response:
    """Every note of a deleted account. Portcullis calls it when an administrator deletes the account."""
    store: DocumentStore = request.app.state.store
    try:
        await purge_owner(store, uid)
    except DbGatewayError as error:
        _fail(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
