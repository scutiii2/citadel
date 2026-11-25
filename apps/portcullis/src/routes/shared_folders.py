"""Temporary shared folders. `router` is for the logged-in account (folders.use): open, list and delete
its folders and remove files. `public_router` is the one place files can be read and added without
logging in, through the folder's link: list and download, and add. Guests never remove anything.
The rules live in services/shared_folder_service.py."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.deps import get_db_session, get_log_writer, get_settings, get_share_limiter, require_permission
from src.models import Account, SharedFolder, SharedFolderFile
from src.security import client_ip
from src.services.log_service import LogWriter
from src.services.permissions import FOLDERS_USE
from src.services.public_rate_limiter import PublicReadLimiter
from src.services.shared_folder_service import (
    MAX_FILE_BYTES, MAX_MINUTES, FolderLimit, FolderNotFound, SharedFolderService, iso)

router = APIRouter(prefix="/api/shared-folders", tags=["shared-folders"])
public_router = APIRouter(prefix="/api/folder-links", tags=["shared-folders"])

require_folders = require_permission(FOLDERS_USE)
_NO_STORE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}


def get_folders(session: AsyncSession = Depends(get_db_session), settings: Settings = Depends(get_settings)) -> SharedFolderService:
    return SharedFolderService(session, settings.database_path.parent / "shared_folders")


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    # How long the folder lives from now, in minutes. Never extended later.
    minutes: int = Field(default=MAX_MINUTES, ge=1, le=MAX_MINUTES)


class FileOut(BaseModel):
    id: int
    name: str
    size: int
    created_at: str

    @classmethod
    def of(cls, row: SharedFolderFile) -> "FileOut":
        return cls(id=row.id, name=row.name, size=row.size, created_at=iso(row.created_at))


class FolderOut(BaseModel):
    id: int
    name: str
    token: str
    created_at: str
    expires_at: str
    files: list[FileOut]

    @classmethod
    def of(cls, folder: SharedFolder, files: list[SharedFolderFile]) -> "FolderOut":
        return cls(id=folder.id, name=folder.name, token=folder.token, created_at=iso(folder.created_at),
                   expires_at=iso(folder.expires_at), files=[FileOut.of(row) for row in files])


class PublicFolderOut(BaseModel):
    """What a guest sees: no owner, no token, no ids of other folders."""

    name: str
    expires_at: str
    max_file_bytes: int
    files: list[FileOut]


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")


def _limit(error: FolderLimit) -> HTTPException:
    code = status.HTTP_413_CONTENT_TOO_LARGE if error.too_large else status.HTTP_409_CONFLICT
    return HTTPException(code, str(error))


# --- the account's own folders ------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: CreateFolderRequest,
    account: Account = Depends(require_folders),
    folders: SharedFolderService = Depends(get_folders),
    logs: LogWriter = Depends(get_log_writer),
) -> FolderOut:
    try:
        folder = await folders.create(account, body.name.strip() or "Folder", body.minutes)
    except FolderLimit as error:
        raise _limit(error) from error
    await logs.action(account, "folders.create", f"Opened shared folder {folder.id} for {body.minutes} min")
    return FolderOut.of(folder, [])


@router.get("")
async def list_folders(account: Account = Depends(require_folders),
                       folders: SharedFolderService = Depends(get_folders)) -> list[FolderOut]:
    """The account's open folders, newest first, with their files and links."""
    return [FolderOut.of(folder, files) for folder, files in await folders.list_for(account)]


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: int, account: Account = Depends(require_folders),
                        folders: SharedFolderService = Depends(get_folders),
                        logs: LogWriter = Depends(get_log_writer)) -> Response:
    """Ends the folder now: the link stops working and the files are wiped."""
    try:
        await folders.delete_folder(account, folder_id)
    except FolderNotFound as error:
        raise _not_found() from error
    await logs.action(account, "folders.delete", f"Deleted shared folder {folder_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{folder_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(folder_id: int, file_id: int, account: Account = Depends(require_folders),
                      folders: SharedFolderService = Depends(get_folders),
                      logs: LogWriter = Depends(get_log_writer)) -> Response:
    try:
        await folders.delete_file(account, folder_id, file_id)
    except FolderNotFound as error:
        raise _not_found() from error
    await logs.action(account, "folders.file.delete", f"Removed file {file_id} from shared folder {folder_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- anyone with the link -----------------------------------------------------------


def _check_rate(request: Request, limiter: PublicReadLimiter) -> None:
    wait = limiter.retry_after(client_ip(request))
    if wait is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests - wait a moment",
                            headers={"Retry-After": str(wait)})


@public_router.get("/{token}")
async def read_folder(token: str, request: Request, response: Response,
                      folders: SharedFolderService = Depends(get_folders),
                      limiter: PublicReadLimiter = Depends(get_share_limiter)) -> PublicFolderOut:
    """No login. An unknown, malformed, deleted or expired link all give the same 404."""
    _check_rate(request, limiter)
    try:
        folder = await folders.by_token(token)
    except FolderNotFound as error:
        raise _not_found() from error
    response.headers.update(_NO_STORE)
    return PublicFolderOut(name=folder.name, expires_at=iso(folder.expires_at), max_file_bytes=MAX_FILE_BYTES,
                           files=[FileOut.of(row) for row in await folders.files(folder)])


@public_router.get("/{token}/files/{file_id}")
async def download_file(token: str, file_id: int, request: Request,
                        folders: SharedFolderService = Depends(get_folders),
                        limiter: PublicReadLimiter = Depends(get_share_limiter)) -> FileResponse:
    """The bytes as an attachment, never rendered by the browser (`octet-stream`, `nosniff`)."""
    _check_rate(request, limiter)
    try:
        folder = await folders.by_token(token)
        row = await folders.file(folder, file_id)
    except FolderNotFound as error:
        raise _not_found() from error
    path: Path = folders.file_path(folder.id, row.id)
    if not path.is_file():
        raise _not_found()
    return FileResponse(path, media_type="application/octet-stream", filename=row.name,
                        headers={**_NO_STORE, "X-Content-Type-Options": "nosniff"})


@public_router.put("/{token}/files", status_code=status.HTTP_201_CREATED)
async def add_file(token: str, request: Request, name: str = Query(min_length=1, max_length=255),
                   folders: SharedFolderService = Depends(get_folders),
                   limiter: PublicReadLimiter = Depends(get_share_limiter)) -> FileOut:
    """The request body is the file itself, streamed to disk (no multipart, no JSON). A guest may add; there is no way to remove."""
    _check_rate(request, limiter)
    try:
        folder = await folders.by_token(token)
    except FolderNotFound as error:
        raise _not_found() from error
    length = request.headers.get("content-length", "")
    try:
        row = await folders.add_file(folder, name, request.stream(), int(length) if length.isdigit() else None)
    except FolderLimit as error:
        raise _limit(error) from error
    return FileOut.of(row)
