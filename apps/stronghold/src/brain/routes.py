"""/stack: the user's door to a chat's short-term memory. Portcullis serves it as /api/chats/{id}/stack."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field

from src.agents.gateway import Caller
from src.brain.compaction import CompactionError
from src.brain.stack import StackError
from src.requester import Requester, current_requester

router = APIRouter(prefix="/stack", tags=["stack"])
ChatId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
ItemId = Annotated[int, Path(gt=0)]


class NewItem(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    pinned: bool = False


class PinBody(BaseModel):
    pinned: bool


async def _own_chat(request: Request, requester: Requester, chat_id: str) -> None:
    if not await request.app.state.chats.exists(requester.uid, chat_id):
        raise HTTPException(404, "No such chat.")


def _refuse(error: StackError) -> HTTPException:
    return HTTPException(error.status, str(error))


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(request: Request, uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]) -> Response:
    await request.app.state.stacks.purge_owner(uid)
    return Response(status_code=204)


@router.get("/{chat_id}")
async def view(chat_id: ChatId, request: Request, requester: Requester = Depends(current_requester)):
    await _own_chat(request, requester, chat_id)
    return await request.app.state.stacks.view(requester.uid, chat_id)


@router.post("/{chat_id}/items", status_code=201)
async def add(chat_id: ChatId, body: NewItem, request: Request, requester: Requester = Depends(current_requester)):
    await _own_chat(request, requester, chat_id)
    try:
        return await request.app.state.stacks.add(requester.uid, chat_id, body.text, pinned=body.pinned, source="user")
    except StackError as error:
        raise _refuse(error) from error


@router.put("/{chat_id}/items/{item_id}")
async def pin(chat_id: ChatId, item_id: ItemId, body: PinBody, request: Request,
              requester: Requester = Depends(current_requester)):
    await _own_chat(request, requester, chat_id)
    try:
        return await request.app.state.stacks.pin(requester.uid, chat_id, item_id, body.pinned)
    except StackError as error:
        raise _refuse(error) from error


@router.delete("/{chat_id}/items/{item_id}", status_code=204)
async def remove(chat_id: ChatId, item_id: ItemId, request: Request, requester: Requester = Depends(current_requester)):
    await _own_chat(request, requester, chat_id)
    try:
        await request.app.state.stacks.remove(requester.uid, chat_id, item_id)
    except StackError as error:
        raise _refuse(error) from error
    return Response(status_code=204)


@router.post("/{chat_id}/compact")
async def compact(chat_id: ChatId, request: Request, requester: Requester = Depends(current_requester)):
    await _own_chat(request, requester, chat_id)
    caller = Caller(requester.username, requester.email, requester.uid)
    try:
        outcome = await request.app.state.compactor.compact(requester.uid, chat_id, caller)
    except CompactionError as error:
        raise HTTPException(502, str(error)) from error
    view_now = await request.app.state.stacks.view(requester.uid, chat_id)
    await request.app.state.platform.log_action(requester.uid, "stack.compact", "Compacted short-term memory")
    return {"compacted": outcome is not None, "replaced": outcome.replaced if outcome else 0, **view_now}
