"""The signed-in account's learned skills: review what the assistant proposed, approve, retire, delete.

Approving here is the only way a skill becomes usable; no agent tool can do it.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field, field_validator

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.services.log_service import LogWriter
from src.services.permissions import CHAT_USE
from src.services.skills import Skill, SkillsClient, SkillsError

router = APIRouter(prefix="/api/skills", tags=["skills"])
require_chat = require_permission(CHAT_USE)
SkillId = Annotated[int, Path(gt=0)]


class StatusBody(BaseModel):
    status: Literal["proposed", "active", "retired"]


class EditBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    when_to_use: str = Field(min_length=1, max_length=300)
    steps: str = Field(min_length=1, max_length=1200)
    tools: str = Field(default="", max_length=200)

    @field_validator("title", "when_to_use", "steps", "tools")
    @classmethod
    def clean(cls, value: str, info) -> str:
        clean = " ".join(value.split())
        if not clean and info.field_name != "tools":
            raise ValueError("Cannot be empty")
        return clean


def get_skills(request: Request) -> SkillsClient:
    return request.app.state.skills


@router.get("", response_model=list[Skill])
async def list_skills(account: Account = Depends(require_chat), skills: SkillsClient = Depends(get_skills)):
    try:
        return await skills.list(account.uid)
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error


@router.put("/{skill_id}/status", response_model=Skill)
async def set_skill_status(skill_id: SkillId, body: StatusBody, account: Account = Depends(require_chat),
                           skills: SkillsClient = Depends(get_skills), logs: LogWriter = Depends(get_log_writer)):
    try:
        skill = await skills.set_status(account.uid, skill_id, body.status)
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error
    await logs.action(account, "skills.status", f"Set a skill to {body.status}")
    return skill


@router.put("/{skill_id}", response_model=Skill)
async def edit_skill(skill_id: SkillId, body: EditBody, account: Account = Depends(require_chat),
                     skills: SkillsClient = Depends(get_skills), logs: LogWriter = Depends(get_log_writer)):
    try:
        skill = await skills.update(account.uid, skill_id, body.model_dump())
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error
    await logs.action(account, "skills.edit", "Edited a skill")
    return skill


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: SkillId, account: Account = Depends(require_chat),
                       skills: SkillsClient = Depends(get_skills), logs: LogWriter = Depends(get_log_writer)):
    try:
        await skills.delete(account.uid, skill_id)
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error
    await logs.action(account, "skills.delete", "Deleted a skill")
    return Response(status_code=204)
