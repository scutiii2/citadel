"""/api/brain/shares, /api/brain/blocks and /api/brain/global: sharing and the global brain, answered by Stronghold.
Only a signed-in session reaches them (chat.use); the global write routes also need brain.global.write.
Outside clients must never be given these routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.chats import require_chat
from src.routes.stronghold import pass_on
from src.services.permissions import BRAIN_GLOBAL_WRITE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/brain", tags=["brain-sharing"])
Hex = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
Uid = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
SkillId = Annotated[int, Path(gt=0)]
require_writer = require_permission(BRAIN_GLOBAL_WRITE)


@router.post("/shares")
async def create_share(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/shares")


@router.get("/shares/sent")
async def sent_shares(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/shares/sent")


@router.get("/shares/inbox")
async def inbox_shares(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/shares/inbox")


@router.get("/shares/{share_id}")
async def read_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/shares/{share_id}")


@router.delete("/shares/{share_id}")
async def revoke_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/shares/{share_id}")


@router.post("/shares/{share_id}/accept")
async def accept_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/shares/{share_id}/accept")


@router.post("/shares/{share_id}/decline")
async def decline_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/shares/{share_id}/decline")


@router.get("/blocks")
async def list_blocks(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/blocks")


@router.put("/blocks")
async def block_account(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/blocks")


@router.delete("/blocks/{uid}")
async def unblock_account(
    uid: Uid, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/blocks/{uid}")


@router.get("/global/files")
async def list_global_files(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/files")


@router.get("/global/files/{file_id}")
async def read_global_file(
    file_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/files/{file_id}")


@router.get("/global/search")
async def search_global_files(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/search")


@router.get("/global/summary")
async def global_summary(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/summary")


@router.get("/global/skills")
async def active_global_skills(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/skills")


@router.post("/global/files", dependencies=[Depends(require_writer)])
async def create_global_file(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/files")


@router.put("/global/files/{file_id}", dependencies=[Depends(require_writer)])
async def update_global_file(
    file_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/files/{file_id}")


@router.delete("/global/files/{file_id}", dependencies=[Depends(require_writer)])
async def delete_global_file(
    file_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/files/{file_id}")


@router.get("/global/skills/all", dependencies=[Depends(require_writer)])
async def all_global_skills(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/skills/all")


@router.put("/global/skills/{skill_id}/status", dependencies=[Depends(require_writer)])
async def set_global_skill_status(
    skill_id: SkillId, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/skills/{skill_id}/status")


@router.put("/global/skills/{skill_id}", dependencies=[Depends(require_writer)])
async def update_global_skill(
    skill_id: SkillId, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/skills/{skill_id}")


@router.delete("/global/skills/{skill_id}", dependencies=[Depends(require_writer)])
async def delete_global_skill(
    skill_id: SkillId, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/skills/{skill_id}")


@router.get("/global/shares", dependencies=[Depends(require_writer)])
async def global_share_queue(
    request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, "/brain/global/shares")


@router.get("/global/shares/{share_id}", dependencies=[Depends(require_writer)])
async def read_global_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/shares/{share_id}")


@router.post("/global/shares/{share_id}/approve", dependencies=[Depends(require_writer)])
async def approve_global_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/shares/{share_id}/approve")


@router.post("/global/shares/{share_id}/reject", dependencies=[Depends(require_writer)])
async def reject_global_share(
    share_id: Hex, request: Request, account: Account = Depends(require_chat),
    stronghold: StrongholdForwarder = Depends(get_stronghold),
) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/global/shares/{share_id}/reject")
