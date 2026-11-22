"""/api/brain: the account's long-term memory, kept by Stronghold as Markdown files."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from src.deps import get_stronghold
from src.models import Account
from src.routes.chats import require_chat
from src.routes.stronghold import pass_on
from src.services.stronghold_forwarder import StrongholdForwarder

router = APIRouter(prefix="/api/brain", tags=["brain"])
FileId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]


@router.api_route("/files", methods=["GET", "POST"])
async def files(request: Request, account: Account = Depends(require_chat),
                stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brain/files")


@router.api_route("/files/{file_id}", methods=["GET", "PUT", "DELETE"])
async def one_file(file_id: FileId, request: Request, account: Account = Depends(require_chat),
                   stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/files/{file_id}")


@router.post("/files/{file_id}/revert")
async def revert(file_id: FileId, request: Request, account: Account = Depends(require_chat),
                 stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, f"/brain/files/{file_id}/revert")


@router.get("/search")
async def search(request: Request, account: Account = Depends(require_chat),
                 stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brain/search")


@router.get("/summary")
async def summary(request: Request, account: Account = Depends(require_chat),
                  stronghold: StrongholdForwarder = Depends(get_stronghold)) -> Response:
    return await pass_on(request, stronghold, account, "/brain/summary")
