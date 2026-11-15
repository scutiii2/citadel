"""/api/notes: the logged-in account's private notes, answered by Stronghold.

Portcullis checks the login and the chat.use permission, then passes the request on.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/notes", tags=["notes"])
require_chat = require_permission(CHAT_USE)

# A note id (32 hex) or one of the fixed names. One segment only, so Stronghold's
# /notes/accounts/<uid> purge route is out of reach from here.
_SEGMENT = re.compile(r"[0-9a-f]{32}|tags|suggest-tags|generate-tag")


@router.api_route("", methods=["GET", "POST"])
async def notes(request: Request, account: Account = Depends(require_chat),
                stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/notes")


@router.api_route("/{segment}", methods=["GET", "POST", "PUT", "DELETE"])
async def note(segment: str, request: Request, account: Account = Depends(require_chat),
               stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    if not _SEGMENT.fullmatch(segment):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return await pass_on(request, stronghold, account, f"/notes/{segment}")
