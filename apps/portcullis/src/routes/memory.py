"""/api/memory: the signed-in account's assistant memory, answered by Stronghold.

Portcullis checks the login and the chat.use permission, then passes the request on.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/memory", tags=["memory"])
require_chat = require_permission(CHAT_USE)
NoteId = Annotated[int, Path(gt=0)]


@router.api_route("", methods=["GET", "POST"])
async def memories(request: Request, account: Account = Depends(require_chat),
                   stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/memory")


@router.api_route("/{note_id}", methods=["PUT", "DELETE"])
async def memory(note_id: NoteId, request: Request, account: Account = Depends(require_chat),
                 stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/memory/{note_id}")
