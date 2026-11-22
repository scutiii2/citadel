"""/brain/global: the global brain. Anyone signed in reads; `brain.global.write` writes. Portcullis serves it as /api/brain/global."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from src.brain.files_routes import BrainRoute, FileId, NewFile, full, row
from src.brain.global_brain import GLOBAL_UID, GlobalBrain
from src.brain.share_routes import Landing, ShareId, shares_of
from src.brain.access import need, permissions
from src.requester import Requester, current_requester
from src.skills.routes import EditBody, SkillId, SkillOut, StatusBody, _out

WRITE = "brain.global.write"
NOTICE = "Everyone on this instance, and every agent, can read this. Do not put private data here."
_GONE = "This skill no longer exists"

router = APIRouter(prefix="/brain/global", tags=["brain-global"], route_class=BrainRoute)


class GlobalSkillChange(SkillOut):
    notice: str = NOTICE


class GlobalChange(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=100_000)
    tags: list[str] | None = Field(default=None, max_length=50)
    folder: str | None = Field(default=None, max_length=130)
    expected_revision: int | None = Field(default=None, ge=1)


def _global(request: Request) -> GlobalBrain:
    return request.app.state.global_brain


async def writer(who: Requester = Depends(current_requester), granted: set[str] = Depends(permissions)) -> Requester:
    need(granted, WRITE)
    return who


async def _logged(request: Request, who: Requester) -> None:
    await request.app.state.platform.log_action(who.uid, "brain.global_write", "Changed the global brain")


@router.get("/files")
async def list_files(request: Request, folder: Annotated[str | None, Query(max_length=130)] = None,
                     _who: Requester = Depends(current_requester)):
    files = _global(request).files
    return {"files": [row(r) for r in await files.list(GLOBAL_UID, folder)], "folders": await files.folders(GLOBAL_UID)}


@router.get("/files/{file_id}")
async def read_file(file_id: FileId, request: Request, _who: Requester = Depends(current_requester)):
    return full(await _global(request).files.get(GLOBAL_UID, file_id))


@router.get("/search")
async def search(request: Request, q: Annotated[str, Query(min_length=1, max_length=200)],
                 limit: Annotated[int | None, Query(ge=1, le=30)] = None, _who: Requester = Depends(current_requester)):
    hits = await _global(request).files.search(GLOBAL_UID, q, limit)
    return {"results": [{**row(hit.record), "score": hit.score, "snippet": hit.snippet} for hit in hits]}


@router.get("/summary")
async def summary(request: Request, _who: Requester = Depends(current_requester)):
    return {**await _global(request).files.summary(GLOBAL_UID), "notice": NOTICE}


@router.post("/files", status_code=201)
async def create_file(body: NewFile, request: Request, who: Requester = Depends(writer)):
    made = await _global(request).files.create(GLOBAL_UID, title=body.title, body=body.body, tags=body.tags, folder=body.folder)
    await _logged(request, who)
    return {**full(made), "notice": NOTICE}


@router.put("/files/{file_id}")
async def change_file(file_id: FileId, body: GlobalChange, request: Request, who: Requester = Depends(writer)):
    given = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    changed = await _global(request).files.update(GLOBAL_UID, file_id, expected_revision=body.expected_revision, **given)
    await _logged(request, who)
    return {**full(changed), "notice": NOTICE}


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: FileId, request: Request, who: Requester = Depends(writer)) -> Response:
    await _global(request).files.delete(GLOBAL_UID, file_id)
    await _logged(request, who)
    return Response(status_code=204)


@router.get("/skills", response_model=list[SkillOut])
async def active_skills(request: Request, _who: Requester = Depends(current_requester)):
    # What agents are offered: active and not failing. An empty query lists the newest, so ask for the cap.
    return [_out(s) for s in await _global(request).skills.search(GLOBAL_UID, "", 50)]


@router.get("/skills/all", response_model=list[SkillOut])
async def all_skills(request: Request, _who: Requester = Depends(writer)):
    return [_out(s) for s in await _global(request).skills.list(GLOBAL_UID)]


@router.put("/skills/{skill_id}/status", response_model=GlobalSkillChange)
async def skill_status(skill_id: SkillId, body: StatusBody, request: Request, who: Requester = Depends(writer)):
    skill = await _global(request).skills.set_status(GLOBAL_UID, skill_id, body.status)
    if skill is None:
        raise HTTPException(404, _GONE)
    await _logged(request, who)
    return GlobalSkillChange(**_out(skill).model_dump())


@router.put("/skills/{skill_id}", response_model=GlobalSkillChange)
async def edit_skill(skill_id: SkillId, body: EditBody, request: Request, who: Requester = Depends(writer)):
    skill = await _global(request).skills.update(GLOBAL_UID, skill_id, body.title, body.when_to_use, body.steps, body.tools)
    if skill is None:
        raise HTTPException(404, _GONE)
    await _logged(request, who)
    return GlobalSkillChange(**_out(skill).model_dump())


@router.delete("/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: SkillId, request: Request, who: Requester = Depends(writer)) -> Response:
    if not await _global(request).skills.delete(GLOBAL_UID, skill_id):
        raise HTTPException(404, _GONE)
    await _logged(request, who)
    return Response(status_code=204)


@router.get("/shares")
async def queue(request: Request, _who: Requester = Depends(writer)):
    return {"shares": await shares_of(request).queue()}


@router.get("/shares/{share_id}")
async def queued_share(share_id: ShareId, request: Request, who: Requester = Depends(writer)):
    return await shares_of(request).get(who.uid, share_id, reviewer=True)


@router.post("/shares/{share_id}/approve")
async def approve(share_id: ShareId, request: Request, body: Landing | None = None, who: Requester = Depends(writer)):
    given = body or Landing()
    done = await shares_of(request).review(share_id, True, given.title, given.folder)
    await request.app.state.platform.log_action(who.uid, "brain.global_review", "Reviewed a global share")
    return {**done, "notice": NOTICE}


@router.post("/shares/{share_id}/reject")
async def reject(share_id: ShareId, request: Request, who: Requester = Depends(writer)):
    done = await shares_of(request).review(share_id, False)
    await request.app.state.platform.log_action(who.uid, "brain.global_review", "Reviewed a global share")
    return {**done, "notice": NOTICE}
