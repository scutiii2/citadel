"""Session-scoped files on disk with an in-memory index.

Layout: <root>/<sha256(session)[:32]>/<file_id> plus a <file_id>.json
sidecar holding the StoredFile record, so the index can be rebuilt after a
restart. Session strings are hashed so "mcp:alice" or anything a caller
sends can never become a raw path. The user's file name is metadata only.

One instance per process. Index mutations happen on the event loop thread;
disk I/O goes through asyncio.to_thread so the loop never blocks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable
from dataclasses import asdict, dataclass
from pathlib import Path

from src.capabilities.pdf_merger.utils.config import MB
from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError
from src.services.session_file_store import DATA_NAME_RE, WORK_DIR_NAME, SessionFileStore, new_file_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredFile:
    """One committed file. ``kind`` is "pdf" or "image"."""

    file_id: str
    session: str
    name: str
    mime: str
    kind: str
    pages: int
    size: int
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class PendingFile:
    """Content being written; becomes a StoredFile on commit()."""

    file_id: str
    session: str
    path: Path


class FileStore(SessionFileStore):
    file_class = StoredFile

    def _not_found(self, file_id: str) -> Exception:
        return MergerError(ErrorCode.FILE_NOT_FOUND, "This file is not available. Upload it again.")

    def _delete_failed(self) -> Exception:
        return MergerError(ErrorCode.INTERNAL, "This file couldn't be deleted right now. Try again in a moment.")

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
                    raise MergerError(
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
            raise MergerError(
                ErrorCode.LIMIT_EXCEEDED,
                f"Your files would use more than {self._max_session_bytes // MB} MB. Delete some files or wait for them to expire.",
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
