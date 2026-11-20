"""/brain: the user's door to long-term memory. Portcullis serves it as /api/brain."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from src.brain.files import BrainError
from src.brain.records import Record
from src.document_store import DbGatewayError
from src.requester import Requester, current_requester

AGENT_WARNING = "Written by an agent. Editing it may break the agent that uses it."


class BrainRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handle = super().get_route_handler()

        async def safe_response(request: Request) -> Response:
            try:
                return await handle(request)
            except RequestValidationError:
                raise HTTPException(422, "Invalid brain request.") from None
            except BrainError as error:
                raise HTTPException(error.status, str(error)) from None
            except (OSError, DbGatewayError):
                raise HTTPException(503, "Storage is unavailable") from None

        return safe_response


router = APIRouter(prefix="/brain", tags=["brain"], route_class=BrainRoute)
FileId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


class NewFile(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    folder: str = Field(default="", max_length=130)


class FileChange(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=100_000)
    tags: list[str] | None = Field(default=None, max_length=50)
    folder: str | None = Field(default=None, max_length=130)
    agent_editable: bool | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class RevertFile(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)


def row(record: Record) -> dict[str, Any]:
    """A file without its body (list and search rows)."""
    return {
        "id": record.id, "title": record.title, "folder": record.folder, "tags": list(record.tags), "source": record.source,
        "last_editor": record.last_editor, "agent_editable": record.agent_editable, "edited": record.edited,
        "revision": record.revision, "created_at": record.created_at, "updated_at": record.updated_at,
        "chars": len(record.body), "warning": AGENT_WARNING if record.source == "automatic" else None,
        "shared_from": record.shared_from,
    }


def full(record: Record) -> dict[str, Any]:
    shown = row(record)
    del shown["chars"]
    return {**shown, "body": record.body}


def _files(request: Request):
    return request.app.state.brain_files


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(request: Request, uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")]) -> Response:
    await _files(request).purge(uid)
    return Response(status_code=204)


@router.get("/files")
async def list_files(request: Request, folder: Annotated[str | None, Query(max_length=130)] = None,
                     requester: Requester = Depends(current_requester)):
    files = _files(request)
    return {"files": [row(record) for record in await files.list(requester.uid, folder)], "folders": await files.folders(requester.uid)}


@router.post("/files", status_code=201)
async def create_file(body: NewFile, request: Request, requester: Requester = Depends(current_requester)):
    return full(await _files(request).create(requester.uid, title=body.title, body=body.body, tags=body.tags, folder=body.folder))


@router.get("/files/{file_id}")
async def read_file(file_id: FileId, request: Request, requester: Requester = Depends(current_requester)):
    return full(await _files(request).get(requester.uid, file_id))


@router.put("/files/{file_id}")
async def change_file(file_id: FileId, body: FileChange, request: Request, requester: Requester = Depends(current_requester)):
    given = body.model_dump(exclude_unset=True, exclude={"expected_revision"})
    changed = await _files(request).update(requester.uid, file_id, expected_revision=body.expected_revision, **given)
    if body.agent_editable is not None:
        # The action only, never the title or text.
        await request.app.state.platform.log_action(
            requester.uid, "brain.agent_edit", "Let agents edit a file" if changed.agent_editable else "Stopped agents editing a file")
    return full(changed)


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(file_id: FileId, request: Request, requester: Requester = Depends(current_requester)) -> Response:
    await _files(request).delete(requester.uid, file_id)
    return Response(status_code=204)


@router.post("/files/{file_id}/revert")
async def revert_file(file_id: FileId, request: Request, body: RevertFile | None = None,
                      requester: Requester = Depends(current_requester)):
    revision = body.expected_revision if body is not None else None
    return full(await _files(request).revert(requester.uid, file_id, expected_revision=revision))


@router.get("/search")
async def search(request: Request, q: Annotated[str, Query(min_length=1, max_length=200)],
                 limit: Annotated[int | None, Query(ge=1, le=30)] = None, requester: Requester = Depends(current_requester)):
    hits = await _files(request).search(requester.uid, q, limit)
    return {"results": [{**row(hit.record), "score": hit.score, "snippet": hit.snippet} for hit in hits]}


@router.get("/summary")
async def summary(request: Request, requester: Requester = Depends(current_requester)):
    return await _files(request).summary(requester.uid)
