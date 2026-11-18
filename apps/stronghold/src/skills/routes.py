"""/skills: an account's learned skills, kept by Armory: review what the assistant proposed, approve, retire, delete.

Approving here is the only way a skill becomes usable; no agent tool can do it.
Portcullis serves these as /api/skills after checking the login and the chat.use permission.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field, field_validator

from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.skills.client import Skill, SkillsClient, SkillsError

router = APIRouter(prefix="/skills", tags=["skills"])
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


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


@router.get("", response_model=list[Skill])
async def list_skills(requester: Requester = Depends(current_requester), skills: SkillsClient = Depends(get_skills)):
    try:
        return await skills.list(requester.uid)
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error


@router.put("/{skill_id}/status", response_model=Skill)
async def set_skill_status(skill_id: SkillId, body: StatusBody, requester: Requester = Depends(current_requester),
                           skills: SkillsClient = Depends(get_skills), platform: PortcullisClient = Depends(get_platform)):
    try:
        skill = await skills.set_status(requester.uid, skill_id, body.status)
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error
    await platform.log_action(requester.uid, "skills.status", f"Set a skill to {body.status}")
    return skill


@router.put("/{skill_id}", response_model=Skill)
async def edit_skill(skill_id: SkillId, body: EditBody, requester: Requester = Depends(current_requester),
                     skills: SkillsClient = Depends(get_skills), platform: PortcullisClient = Depends(get_platform)):
    try:
        skill = await skills.update(requester.uid, skill_id, body.model_dump())
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error
    await platform.log_action(requester.uid, "skills.edit", "Edited a skill")
    return skill


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        skills: SkillsClient = Depends(get_skills)) -> Response:
    """Everything a deleted account kept. Portcullis calls it; 502 when Armory did not confirm."""
    if not await skills.purge(uid):
        raise HTTPException(502, "Skills were not purged")
    return Response(status_code=204)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: SkillId, requester: Requester = Depends(current_requester),
                       skills: SkillsClient = Depends(get_skills), platform: PortcullisClient = Depends(get_platform)):
    try:
        await skills.delete(requester.uid, skill_id)
    except SkillsError as error:
        raise HTTPException(error.status, str(error)) from error
    await platform.log_action(requester.uid, "skills.delete", "Deleted a skill")
    return Response(status_code=204)
