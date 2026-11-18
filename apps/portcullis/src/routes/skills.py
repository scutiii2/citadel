"""/api/skills: the signed-in account's learned skills, answered by Stronghold.

Portcullis checks the login and the chat.use permission, then passes the request on.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold, require_permission
from src.models import Account
from src.routes.stronghold import pass_on
from src.services.permissions import CHAT_USE
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/skills", tags=["skills"])
require_chat = require_permission(CHAT_USE)
SkillId = Annotated[int, Path(gt=0)]


@router.get("")
async def list_skills(request: Request, account: Account = Depends(require_chat),
                      stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/skills")


@router.put("/{skill_id}/status")
async def set_skill_status(skill_id: SkillId, request: Request, account: Account = Depends(require_chat),
                           stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/skills/{skill_id}/status")


@router.api_route("/{skill_id}", methods=["PUT", "DELETE"])
async def skill(skill_id: SkillId, request: Request, account: Account = Depends(require_chat),
                stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/skills/{skill_id}")
