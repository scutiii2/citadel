"""/api/chats/{id}/stack: a chat's short-term memory, kept by Stronghold."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold
from src.models import Account
from src.routes.chats import require_chat
from src.routes.stronghold import pass_on
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/chats", tags=["stack"])
ChatId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
ItemId = Annotated[int, Path(gt=0)]


@router.get("/{chat_id}/stack")
async def view(chat_id: ChatId, request: Request, account: Account = Depends(require_chat),
               stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/stack/{chat_id}")


@router.post("/{chat_id}/stack/items")
async def add(chat_id: ChatId, request: Request, account: Account = Depends(require_chat),
              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/stack/{chat_id}/items")


@router.put("/{chat_id}/stack/items/{item_id}")
async def pin(chat_id: ChatId, item_id: ItemId, request: Request, account: Account = Depends(require_chat),
              stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/stack/{chat_id}/items/{item_id}")


@router.delete("/{chat_id}/stack/items/{item_id}")
async def remove(chat_id: ChatId, item_id: ItemId, request: Request, account: Account = Depends(require_chat),
                 stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/stack/{chat_id}/items/{item_id}")


@router.post("/{chat_id}/stack/compact")
async def compact(chat_id: ChatId, request: Request, account: Account = Depends(require_chat),
                  stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/stack/{chat_id}/compact")
