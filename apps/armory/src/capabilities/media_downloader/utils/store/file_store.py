"""Session-scoped files on disk with an in-memory index.

Layout: <root>/<sha256(session)[:32]>/<file_id> plus a <file_id>.json sidecar
holding the StoredFile record, so the index can be rebuilt after a restart.
Session strings are hashed so "mcp:alice" or anything a caller sends can never
become a raw path. The video title is metadata only.

Downloads happen in scratch directories under <root>/_work (same volume as the
store, so commit_file can move a finished file with an atomic rename).

One instance per process. Index mutations happen on the event loop thread; disk
I/O goes through asyncio.to_thread so the loop never blocks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from src.capabilities.media_downloader.utils.config import MB
from src.capabilities.media_downloader.utils.errors import DownloaderError, ErrorCode
from src.services.session_file_store import WORK_DIR_NAME, SessionFileStore, new_file_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredFile:
    """One committed file. ``kind`` is video, audio, photo (image/ZIP), or package (ZIP)."""

    file_id: str
    session: str
    name: str
    mime: str
    kind: str
    size: int
    duration: float | None
    created_at: float
    expires_at: float


class FileStore(SessionFileStore):
    file_class = StoredFile

    def _not_found(self, file_id: str) -> Exception:
        return DownloaderError(ErrorCode.FILE_NOT_FOUND, f"File {file_id} wasn't found. It may have expired; download it again.")

    def _delete_failed(self) -> Exception:
        return DownloaderError(ErrorCode.INTERNAL, "This file couldn't be deleted right now. Try again in a moment.")

    def _prepare_scan(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def _accept(self, meta: Path, file: StoredFile) -> bool:
        if not self.path(file).is_file():
            logger.warning("Dropping sidecar %s: its data file is missing", meta)
            meta.unlink(missing_ok=True)
            return False
        return True

    def _clean_stale(self, found: list[StoredFile]) -> None:
        """Delete data files without a sidecar and every scratch directory (no job survives a restart)."""
        self._delete_unknown_data_files(found, drop_parts=False)
        shutil.rmtree(self._root / WORK_DIR_NAME, ignore_errors=True)

    async def commit_file(
        self, session: str, source: Path, *, name: str, mime: str, kind: str, duration: float | None
    ) -> StoredFile:
        """Move a finished download into the store. Enforces the file cap and the session quota.

        On a refusal the source file is deleted, so nothing is left behind.
        """
        size = (await asyncio.to_thread(source.stat)).st_size
        if size > self._max_file_bytes:
            await asyncio.to_thread(source.unlink, True)
            raise DownloaderError(
                ErrorCode.TOO_LARGE, f"The file is larger than {self._max_file_bytes // MB} MB, so it was not kept."
            )
        if self._over_quota(session, size):
            await asyncio.to_thread(source.unlink, True)
            raise DownloaderError(
                ErrorCode.LIMIT_EXCEEDED,
                f"Your files would use more than {self._max_session_bytes // MB} MB. Delete some files or wait for them to expire.",
            )
        # Reserve space synchronously, before any further await.
        self._reserved[session] = self._reserved.get(session, 0) + size
        try:
            now = self._clock()
            stored = StoredFile(
                file_id=new_file_id(),
                session=session,
                name=name,
                mime=mime,
                kind=kind,
                size=size,
                duration=duration,
                created_at=now,
                expires_at=now + self._ttl,
            )

            def finish() -> None:
                self._session_dir(session).mkdir(parents=True, exist_ok=True)
                os.replace(source, self.path(stored))
                self._meta_path(stored).write_text(json.dumps(asdict(stored)), "utf-8")

            await asyncio.to_thread(finish)
            self._index[stored.file_id] = stored
            return stored
        finally:
            self._release(session, size)
