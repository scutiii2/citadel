"""/skills: an account's learned skills, kept in Stronghold's brain folder: review what agents proposed, approve, retire, delete.

Approving here is the only way a skill becomes usable; no agent tool can do it.
Portcullis serves these as /api/skills after checking the login and the chat.use permission.
Skill text is never logged. A refusal from the store (BrainError) is answered by the route as {"detail": ...}.
"""
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator

from src.brain.files import BrainError
from src.brain.skills import Skill, SkillFiles
from src.citadel_auth import current_caller
from src.platform import PortcullisClient
from src.requester import Requester, current_requester


class SkillRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handle = super().get_route_handler()

        async def safe_response(request: Request) -> Response:
            caller = current_caller()
            if caller is None or caller.name != "portcullis":
                raise HTTPException(403, "Only Portcullis may use the skills routes.")
            try:
                return await handle(request)
            except RequestValidationError:
                raise HTTPException(422, "Invalid skill request.") from None
            except BrainError as error:
                raise HTTPException(error.status, str(error)) from None
            except OSError:
                raise HTTPException(503, "Skill storage is unavailable.") from None

        return safe_response


router = APIRouter(prefix="/skills", tags=["skills"], route_class=SkillRoute)
SkillId = Annotated[int, Path(gt=0)]
_GONE = "This skill no longer exists"


class SkillOut(BaseModel):
    id: int
    title: str
    when_to_use: str
    steps: str
    tools: str
    status: Literal["proposed", "active", "retired"]
    successes: int
    failures: int
    created_at: str
    # It failed often and more often than it worked, so agents are no longer offered it.
    failing: bool = False
    shared_from: str = ""


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


def get_skills(request: Request) -> SkillFiles:
    return request.app.state.skill_files


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


def _out(skill: Skill) -> SkillOut:
    return SkillOut(**asdict(skill), failing=skill.failing)


@router.get("", response_model=list[SkillOut])
async def list_skills(requester: Requester = Depends(current_requester), skills: SkillFiles = Depends(get_skills)):
    return [_out(skill) for skill in await skills.list(requester.uid)]


@router.put("/{skill_id}/status", response_model=SkillOut)
async def set_skill_status(skill_id: SkillId, body: StatusBody, requester: Requester = Depends(current_requester),
                           skills: SkillFiles = Depends(get_skills), platform: PortcullisClient = Depends(get_platform)):
    skill = await skills.set_status(requester.uid, skill_id, body.status)
    if skill is None:
        raise HTTPException(404, _GONE)
    await platform.log_action(requester.uid, "skills.status", f"Set a skill to {body.status}")
    return _out(skill)


@router.put("/{skill_id}", response_model=SkillOut)
async def edit_skill(skill_id: SkillId, body: EditBody, requester: Requester = Depends(current_requester),
                     skills: SkillFiles = Depends(get_skills), platform: PortcullisClient = Depends(get_platform)):
    skill = await skills.update(requester.uid, skill_id, body.title, body.when_to_use, body.steps, body.tools)
    if skill is None:
        raise HTTPException(404, _GONE)
    await platform.log_action(requester.uid, "skills.edit", "Edited a skill")
    return _out(skill)


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        skills: SkillFiles = Depends(get_skills)) -> Response:
    """Every skill a deleted account kept. Portcullis calls it. The rest of the brain goes with DELETE /brain/accounts/{uid}."""
    await skills.purge(uid)
    return Response(status_code=204)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: SkillId, requester: Requester = Depends(current_requester),
                       skills: SkillFiles = Depends(get_skills), platform: PortcullisClient = Depends(get_platform)):
    if not await skills.delete(requester.uid, skill_id):
        raise HTTPException(404, _GONE)
    await platform.log_action(requester.uid, "skills.delete", "Deleted a skill")
    return Response(status_code=204)
