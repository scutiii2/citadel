"""/shares: an account's share links, kept in Treasury, and the public read of one.

Portcullis serves these as /api/chats/{id}/shares and /api/shares (chat.share, chat.use), and
GET /api/shared/{token} (no login: Portcullis rate-limits it by address and adds the no-cache
headers). Portcullis also cuts the chat down to what may be shared before it asks for a link.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field

from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.shares.store import ShareLimitError, ShareNotFound, ShareStore

router = APIRouter(prefix="/shares", tags=["shares"])

ShareId = Path(ge=1, le=2**31 - 1)
ChatIdText = Annotated[str, Field(pattern=r"^[A-Za-z0-9-]{8,64}$")]
# secrets.token_urlsafe(32) is 43 characters; anything else cannot be a link.
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,64}$")


def get_shares(request: Request) -> ShareStore:
    return request.app.state.shares


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


class SharedMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class CreateBody(BaseModel):
    chat_id: ChatIdText
    title: str = Field(max_length=120)
    messages: list[SharedMessage] = Field(min_length=1, max_length=10_000)
    # Days until the link stops working; null: it never does.
    expires_in_days: Literal[1, 7, 30] | None = 7


def _out(doc: dict) -> dict:
    return {"id": doc["id"], "chat_id": doc["chat_id"], "title": doc["title"], "message_count": doc["message_count"],
            "created_at": doc["created_at"], "expires_at": doc["expires_at"]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_share(body: CreateBody, who: Requester = Depends(current_requester),
                       shares: ShareStore = Depends(get_shares), platform: PortcullisClient = Depends(get_platform)) -> dict:
    """The response is the only time the link's token is shown."""
    try:
        created = await shares.create(who.uid, body.chat_id, body.title,
                                      [m.model_dump() for m in body.messages], body.expires_in_days)
    except ShareLimitError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    expiry = f"{body.expires_in_days} days" if body.expires_in_days else "no expiry"
    await platform.log_action(who.uid, "share.create", f'Shared chat "{body.title}" (link {created.share["id"]}, {expiry})')
    return {**_out(created.share), "token": created.token}


@router.get("")
async def list_shares(chat_id: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9-]{8,64}$")] = None,
                      who: Requester = Depends(current_requester), shares: ShareStore = Depends(get_shares)) -> list[dict]:
    """This account's active links (never their tokens), newest first; `chat_id` narrows them to one chat."""
    return [_out(doc) for doc in await shares.list(who.uid, chat_id)]


@router.get("/public/{token}")
async def read_shared_chat(token: str, shares: ShareStore = Depends(get_shares)) -> dict:
    """No requester. A link that is unknown, revoked or expired gives the same 404 as one that never existed."""
    doc = await shares.read(token) if _TOKEN_PATTERN.fullmatch(token) else None
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shared chat not found")
    return {"title": doc["title"], "messages": doc["messages"], "created_at": doc["created_at"],
            "expires_at": doc["expires_at"]}


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        shares: ShareStore = Depends(get_shares)) -> Response:
    """Every link of a deleted account. Portcullis calls it when an administrator deletes the account."""
    await shares.purge_owner(uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(share_id: int = ShareId, who: Requester = Depends(current_requester),
                       shares: ShareStore = Depends(get_shares), platform: PortcullisClient = Depends(get_platform)) -> Response:
    try:
        doc = await shares.revoke(who.uid, share_id)
    except ShareNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shared link not found") from error
    await platform.log_action(who.uid, "share.revoke", f'Revoked the link {doc["id"]} to chat "{doc["title"]}"')
    return Response(status_code=status.HTTP_204_NO_CONTENT)
