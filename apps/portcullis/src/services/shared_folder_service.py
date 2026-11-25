"""Temporary shared folders: an account opens one, shares its link, and it is deleted within the hour.

Rules kept here, not in the browser:

* The deadline is fixed at creation (at most `MAX_MINUTES`). Adding or removing files never moves it.
* An expired folder reads as missing at once; the sweeper (`sweep_forever`) only reclaims the disk.
* Guests may read, download and add. Only the owner removes a file or the folder (routes/shared_folders.py).
* Caps: file size, files and bytes per folder, open folders and bytes per account.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import shutil
from collections.abc import AsyncIterable
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import Database, utcnow
from src.models import Account, SharedFolder, SharedFolderFile

logger = logging.getLogger(__name__)

MAX_MINUTES = 60
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FOLDER_BYTES = 500 * 1024 * 1024
MAX_FOLDER_FILES = 50
MAX_OPEN_FOLDERS = 3
MAX_ACCOUNT_BYTES = 1024 * 1024 * 1024
NAME_LENGTH = 120
SWEEP_SECONDS = 30
# secrets.token_urlsafe(32) is 43 characters; anything else cannot be a link.
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{40,64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class FolderNotFound(Exception):
    """No such folder for this caller, or it has expired."""


class FolderLimit(Exception):
    """A cap stops the request. `too_large` marks a file bigger than what is allowed (413, not 409)."""

    def __init__(self, message: str, *, too_large: bool = False) -> None:
        super().__init__(message)
        self.too_large = too_large


def clean_file_name(raw: str) -> str:
    """A guest's file name cut to a plain name: no folders, no control characters, bounded length."""
    name = _CONTROL.sub("", raw.replace("\\", "/").rsplit("/", 1)[-1]).strip().lstrip(".")
    return name[:NAME_LENGTH] or "file"


class SharedFolderService:
    def __init__(self, session: AsyncSession, root: Path) -> None:
        self._session = session
        self._root = root

    def file_path(self, folder_id: int, file_id: int) -> Path:
        return self._root / str(folder_id) / str(file_id)

    # --- the owner ------------------------------------------------------------------

    async def create(self, account: Account, name: str, minutes: int) -> SharedFolder:
        open_now = await self._session.scalar(
            select(func.count()).select_from(SharedFolder).where(
                SharedFolder.account_id == account.id, SharedFolder.expires_at > utcnow()))
        if open_now >= MAX_OPEN_FOLDERS:
            raise FolderLimit(f"You can have {MAX_OPEN_FOLDERS} open folders at a time")
        now = utcnow()
        folder = SharedFolder(account_id=account.id, name=name, token=secrets.token_urlsafe(32),
                              created_at=now, expires_at=now + timedelta(minutes=min(minutes, MAX_MINUTES)))
        self._session.add(folder)
        await self._session.commit()
        return folder

    async def list_for(self, account: Account) -> list[tuple[SharedFolder, list[SharedFolderFile]]]:
        folders = (await self._session.scalars(
            select(SharedFolder).where(SharedFolder.account_id == account.id, SharedFolder.expires_at > utcnow())
            .order_by(SharedFolder.created_at.desc()))).all()
        return [(folder, await self.files(folder)) for folder in folders]

    async def delete_folder(self, account: Account, folder_id: int) -> None:
        folder = await self._owned(account, folder_id)
        await self._remove(folder.id)

    async def delete_file(self, account: Account, folder_id: int, file_id: int) -> None:
        folder = await self._owned(account, folder_id)
        row = await self._session.scalar(
            select(SharedFolderFile).where(SharedFolderFile.id == file_id, SharedFolderFile.folder_id == folder.id))
        if row is None:
            raise FolderNotFound
        await self._session.delete(row)
        await self._session.commit()
        await asyncio.to_thread(self.file_path(folder.id, row.id).unlink, missing_ok=True)

    async def _owned(self, account: Account, folder_id: int) -> SharedFolder:
        folder = await self._session.get(SharedFolder, folder_id)
        if folder is None or folder.account_id != account.id or folder.expires_at <= utcnow():
            raise FolderNotFound
        return folder

    # --- anyone with the link -------------------------------------------------------

    async def by_token(self, token: str) -> SharedFolder:
        folder = await self._session.scalar(select(SharedFolder).where(SharedFolder.token == token)) \
            if TOKEN_PATTERN.fullmatch(token) else None
        if folder is None or folder.expires_at <= utcnow():
            raise FolderNotFound
        return folder

    async def files(self, folder: SharedFolder) -> list[SharedFolderFile]:
        return list((await self._session.scalars(
            select(SharedFolderFile).where(SharedFolderFile.folder_id == folder.id)
            .order_by(SharedFolderFile.created_at, SharedFolderFile.id))).all())

    async def file(self, folder: SharedFolder, file_id: int) -> SharedFolderFile:
        row = await self._session.scalar(
            select(SharedFolderFile).where(SharedFolderFile.id == file_id, SharedFolderFile.folder_id == folder.id))
        if row is None:
            raise FolderNotFound
        return row

    async def add_file(self, folder: SharedFolder, name: str, stream: AsyncIterable[bytes],
                       declared: int | None = None) -> SharedFolderFile:
        """Streams `stream` to disk. Refuses at once when `declared` (Content-Length) is over the room
        left, and stops as soon as the bytes read pass it; a refused or failed upload leaves nothing behind.
        shortcut: caps are checked before the upload, so two uploads at the same moment can pass a folder
        cap by up to one file each; upgrade to a reservation row if that ever matters."""
        used, count = await self._folder_usage(folder.id)
        if count >= MAX_FOLDER_FILES:
            raise FolderLimit(f"This folder holds {MAX_FOLDER_FILES} files at most")
        limit, reason, too_large = await self._room(folder, used)
        if declared is not None and declared > limit:
            raise FolderLimit(reason, too_large=too_large)
        folder_id = folder.id
        await self._session.rollback()  # ends the read transaction: it would block every writer during the upload
        # Written to a temporary name first and renamed once the row has its id, so no database write
        # lock is held while a slow upload streams in.
        part = self._root / str(folder_id) / f".part-{secrets.token_hex(8)}"
        size = 0
        try:
            await asyncio.to_thread(part.parent.mkdir, parents=True, exist_ok=True)
            handle = await asyncio.to_thread(part.open, "wb")
            try:
                async for chunk in stream:
                    size += len(chunk)
                    if size > limit:
                        raise FolderLimit(reason, too_large=too_large)
                    await asyncio.to_thread(handle.write, chunk)
            finally:
                await asyncio.to_thread(handle.close)
            if size == 0:
                raise FolderLimit("The file is empty")
            row = SharedFolderFile(folder_id=folder_id, name=clean_file_name(name), size=size)
            self._session.add(row)
            await self._session.flush()
            await asyncio.to_thread(part.replace, self.file_path(folder_id, row.id))
            await self._session.commit()
        except BaseException:
            await self._session.rollback()
            await asyncio.to_thread(part.unlink, missing_ok=True)
            raise
        return row

    async def _room(self, folder: SharedFolder, used: int) -> tuple[int, str, bool]:
        """The most one more file may hold, why, and whether that cap is the file size."""
        account_used = await self._session.scalar(
            select(func.coalesce(func.sum(SharedFolderFile.size), 0))
            .join(SharedFolder, SharedFolder.id == SharedFolderFile.folder_id)
            .where(SharedFolder.account_id == folder.account_id, SharedFolder.expires_at > utcnow()))
        caps = [
            (MAX_FILE_BYTES, f"A file can be {MAX_FILE_BYTES // 2**20} MB at most", True),
            (MAX_FOLDER_BYTES - used, "This folder is full", False),
            (MAX_ACCOUNT_BYTES - account_used, "The owner's folders are full", False),
        ]
        return min(caps, key=lambda cap: cap[0])

    async def _folder_usage(self, folder_id: int) -> tuple[int, int]:
        used, count = (await self._session.execute(
            select(func.coalesce(func.sum(SharedFolderFile.size), 0), func.count())
            .where(SharedFolderFile.folder_id == folder_id))).one()
        return used, count

    # --- the sweeper ----------------------------------------------------------------

    async def purge_expired(self) -> int:
        """Deletes every expired folder with its files, and any folder directory the database does not know."""
        ids = (await self._session.scalars(
            select(SharedFolder.id).where(SharedFolder.expires_at <= utcnow()))).all()
        for folder_id in ids:
            await self._remove(folder_id)
        live = set((await self._session.scalars(select(SharedFolder.id))).all())
        await asyncio.to_thread(self._drop_orphans, live)
        return len(ids)

    async def _remove(self, folder_id: int) -> None:
        await self._session.execute(delete(SharedFolderFile).where(SharedFolderFile.folder_id == folder_id))
        await self._session.execute(delete(SharedFolder).where(SharedFolder.id == folder_id))
        await self._session.commit()
        await asyncio.to_thread(shutil.rmtree, self._root / str(folder_id), True)

    def _drop_orphans(self, live: set[int]) -> None:
        if not self._root.is_dir():
            return
        for child in self._root.iterdir():
            if not child.name.isdigit() or int(child.name) not in live:
                shutil.rmtree(child, ignore_errors=True)


async def sweep_forever(database: Database, root: Path, every: float = SWEEP_SECONDS) -> None:
    """Runs `purge_expired` now and then every `every` seconds, until cancelled."""
    while True:
        try:
            async with database.sessions() as session:
                await SharedFolderService(session, root).purge_expired()
        except Exception:  # a failed pass must not end the loop; the next one retries
            logger.exception("shared folder sweep failed")
        await asyncio.sleep(every)


def iso(moment: datetime) -> str:
    """A naive UTC time as ISO text with the Z the browser needs."""
    return moment.isoformat() + "Z"
