"""Session-scoped files on disk with an in-memory index.
Layout: <root>/<sha256(session)[:32]>/<file_id> plus a <file_id>.json sidecar; one instance per process, disk I/O off the loop."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable
from dataclasses import asdict, dataclass
from pathlib import Path

from src.services.file_errors import ErrorCode, FileError
from src.services.session_file_store import DATA_NAME_RE, FULL_MESSAGE, WORK_DIR_NAME, SessionFileStore, new_file_id

MB = 1024 * 1024

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredFile:
    """One committed file. ``session`` is the owner's account id; ``pages`` is 0 for a kind without pages."""

    file_id: str
    session: str
    name: str
    mime: str
    kind: str
    pages: int
    size: int
    created_at: float
    expires_at: float
    holders: tuple[str, ...] = ()  # the chats that keep this file


@dataclass(frozen=True)
class PendingFile:
    """Content being written; becomes a StoredFile on commit()."""

    file_id: str
    session: str
    path: Path


class FileStore(SessionFileStore):
    file_class = StoredFile

    def _not_found(self, file_id: str) -> Exception:
        return FileError(ErrorCode.FILE_NOT_FOUND, "This file is not available. Upload it again.")

    def _delete_failed(self) -> Exception:
        return FileError(ErrorCode.INTERNAL, "This file couldn't be deleted right now. Try again in a moment.")

    def _valid_id(self, file_id: str) -> bool:
        return bool(DATA_NAME_RE.fullmatch(file_id))

    def _clean_stale(self, found: list[StoredFile]) -> None:
        """Delete leftovers of a crash: *.part, data files without a sidecar, empty _work dirs."""
        self._delete_unknown_data_files(found, drop_parts=True)
        for work in (self._root / WORK_DIR_NAME).glob("*"):
            if work.is_dir():
                try:
                    work.rmdir()  # only succeeds when empty
                except OSError:
                    pass

    # --- writing -----------------------------------------------------------

    def new_pending(self, session: str) -> PendingFile:
        directory = self._session_dir(session)
        directory.mkdir(parents=True, exist_ok=True)
        file_id = new_file_id()
        return PendingFile(file_id=file_id, session=session, path=directory / f"{file_id}.part")

    async def write_stream(self, session: str, chunks: AsyncIterable[bytes]) -> PendingFile:
        """Stream chunks to disk, stopping as soon as the per-file limit is passed."""
        pending = self.new_pending(session)
        size = 0
        handle = await asyncio.to_thread(open, pending.path, "wb")
        try:
            async for chunk in chunks:
                size += len(chunk)
                if size > self._max_file_bytes:
                    raise FileError(
                        ErrorCode.FILE_TOO_LARGE,
                        f"This file is larger than {self._max_file_bytes // MB} MB. Split or compress it, then upload it again.",
                    )
                await asyncio.to_thread(handle.write, chunk)
        except BaseException:
            await asyncio.to_thread(handle.close)
            self.discard(pending)
            raise
        await asyncio.to_thread(handle.close)
        return pending

    def discard(self, pending: PendingFile) -> None:
        pending.path.unlink(missing_ok=True)

    async def commit(self, pending: PendingFile, *, name: str, mime: str, kind: str, pages: int) -> StoredFile:
        """Register written content. Enforces the session quota."""
        size = (await asyncio.to_thread(pending.path.stat)).st_size
        if self._over_quota(pending.session, size):
            self.discard(pending)
            raise FileError(
                ErrorCode.LIMIT_EXCEEDED,
                FULL_MESSAGE.format(mb=self._max_session_bytes // MB),
            )
        # Synchronously reserve space before any further awaits
        self._reserved[pending.session] = self._reserved.get(pending.session, 0) + size
        try:
            now = self._clock()
            stored = StoredFile(
                file_id=pending.file_id,
                session=pending.session,
                name=name,
                mime=mime,
                kind=kind,
                pages=pages,
                size=size,
                created_at=now,
                expires_at=now + self._ttl,
            )

            def finish() -> None:
                os.replace(pending.path, self.path(stored))
                self._meta_path(stored).write_text(json.dumps(asdict(stored)), "utf-8")

            await asyncio.to_thread(finish)
            self._index[stored.file_id] = stored
            return stored
        finally:
            self._release(pending.session, size)
