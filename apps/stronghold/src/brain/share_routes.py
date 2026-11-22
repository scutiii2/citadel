"""/brain/shares and /brain/blocks: send a snapshot to another account or to the global brain, answer what arrives, block senders.
Portcullis serves them as /api/brain/shares and /api/brain/blocks. Only a signed-in person reaches them; agents have no tool for this."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field, model_validator

from src.brain.files import BrainError
from src.brain.files_routes import BrainRoute
from src.brain.shares import BrainShares
from src.platform import PlatformError
from src.requester import Requester, current_requester

router = APIRouter(prefix="/brain/shares", tags=["brain-shares"], route_class=BrainRoute)
blocks_router = APIRouter(prefix="/brain/blocks", tags=["brain-shares"], route_class=BrainRoute)
ShareId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Username = Annotated[str, Field(min_length=1, max_length=80)]


class NewShare(BaseModel):
    kind: Literal["file", "section", "skill", "stack_item"]
    file_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    heading: str | None = Field(default=None, min_length=1, max_length=200)
    skill_id: int | None = Field(default=None, ge=1)
    chat_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    item_id: int | None = Field(default=None, ge=1)
    recipient: Username | None = None
    to_global: bool = False

    @model_validator(mode="after")
    def complete(self) -> "NewShare":
        if (self.recipient is None) == (not self.to_global):
            raise ValueError("Name one recipient or choose the global brain.")
        needs = {"file": ("file_id",), "section": ("file_id", "heading"), "skill": ("skill_id",), "stack_item": ("chat_id", "item_id")}
        if any(getattr(self, name) is None for name in needs[self.kind]):
            raise ValueError("The share does not say what to share.")
        return self

    def ref(self) -> dict[str, Any]:
        return {"file_id": self.file_id, "heading": self.heading, "skill_id": self.skill_id,
                "chat_id": self.chat_id, "item_id": self.item_id}


class Landing(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    folder: str | None = Field(default=None, max_length=130)


class NewBlock(BaseModel):
    username: Username


def shares_of(request: Request) -> BrainShares:
    return request.app.state.brain_shares


async def resolve(request: Request, username: str) -> tuple[str, str]:
    """(uid, username) of a usable account, or the one refusal every kind of failure shares."""
    try:
        found = await request.app.state.platform.uid_for_username(username)
    except PlatformError:
        raise HTTPException(503, "Portcullis is unavailable") from None
    if found is None:
        raise BrainError(404, "No such recipient.")
    return found


async def _logged(request: Request, who: Requester, action: str, message: str) -> None:
    await request.app.state.platform.log_action(who.uid, action, message)


@router.post("", status_code=201)
async def create_share(body: NewShare, request: Request, who: Requester = Depends(current_requester)):
    recipient_uid, recipient_name = (None, "") if body.to_global else await resolve(request, body.recipient)
    made = await shares_of(request).create(who.uid, who.username, body.kind, body.ref(),
                                           recipient_uid=recipient_uid, recipient_name=recipient_name)
    await _logged(request, who, "brain.share", "Shared something")
    return made


@router.get("/sent")
async def sent(request: Request, who: Requester = Depends(current_requester)):
    return {"shares": await shares_of(request).sent(who.uid)}


@router.get("/inbox")
async def inbox(request: Request, who: Requester = Depends(current_requester)):
    return {"shares": await shares_of(request).inbox(who.uid)}


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(request: Request, uid: Uid) -> Response:
    await shares_of(request).purge(uid)
    return Response(status_code=204)


@router.get("/{share_id}")
async def one_share(share_id: ShareId, request: Request, who: Requester = Depends(current_requester)):
    return await shares_of(request).get(who.uid, share_id)


@router.delete("/{share_id}")
async def revoke(share_id: ShareId, request: Request, who: Requester = Depends(current_requester)):
    done = await shares_of(request).revoke(who.uid, share_id)
    await _logged(request, who, "brain.share_revoke", "Withdrew a share")
    return done


@router.post("/{share_id}/accept")
async def accept(share_id: ShareId, request: Request, body: Landing | None = None, who: Requester = Depends(current_requester)):
    given = body or Landing()
    done = await shares_of(request).accept(who.uid, share_id, given.title, given.folder)
    await _logged(request, who, "brain.share_accept", "Accepted a share")
    return done


@router.post("/{share_id}/decline")
async def decline(share_id: ShareId, request: Request, who: Requester = Depends(current_requester)):
    done = await shares_of(request).decline(who.uid, share_id)
    await _logged(request, who, "brain.share_decline", "Declined a share")
    return done


@blocks_router.get("")
async def list_blocks(request: Request, who: Requester = Depends(current_requester)):
    return {"blocks": await shares_of(request).blocks(who.uid)}


@blocks_router.put("")
async def block(body: NewBlock, request: Request, who: Requester = Depends(current_requester)):
    blocked_uid, blocked_name = await resolve(request, body.username)
    await shares_of(request).block(who.uid, blocked_uid, blocked_name)
    await _logged(request, who, "brain.block", "Blocked an account")
    return {"blocks": await shares_of(request).blocks(who.uid)}


@blocks_router.delete("/{uid}", status_code=204)
async def unblock(uid: Uid, request: Request, who: Requester = Depends(current_requester)) -> Response:
    await shares_of(request).unblock(who.uid, uid)
    await _logged(request, who, "brain.unblock", "Unblocked an account")
    return Response(status_code=204)
