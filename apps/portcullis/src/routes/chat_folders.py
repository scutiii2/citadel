"""/api/chat-folders: the logged-in account's chat folders (chat.use).

Stronghold (`apps/stronghold/src/chats`) keeps the folders, checks the names and limits, and logs the
changes. Portcullis checks the login and permission, and tells Stronghold which of the account's chats
have an answer being written when a folder is deleted, so a live answer is never cut off.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from src.deps import get_stronghold, get_turns, require_permission
from src.models import Account
from src.routes.stronghold import as_response, pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder
from src.services.turns import TurnRegistry

router = APIRouter(prefix="/api/chat-folders", tags=["chat-folders"])

require_chat = require_permission(CHAT_USE)


@router.get("")
async def list_folders(request: Request, account: Account = Depends(require_chat),
                       stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/chat-folders")


@router.post("", status_code=201)
async def create_folder(request: Request, account: Account = Depends(require_chat),
                        stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/chat-folders")


@router.patch("/{folder_id}")
async def update_folder(folder_id: int, request: Request, account: Account = Depends(require_chat),
                        stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/chat-folders/{folder_id}")


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, account: Account = Depends(require_chat),
                        turns: TurnRegistry = Depends(get_turns),
                        stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    """Deletes the folder and every chat in it, after revoking their share links. Refused while one of
    those chats has an answer being written."""
    return as_response(await stronghold.forward(
        "DELETE", f"/chat-folders/{folder_id}", account, json={"running": sorted(turns.running_chat_ids(account.id))}))
