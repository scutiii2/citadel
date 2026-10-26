"""Session-scoped files on disk with an in-memory index, shared by pdf_merger and media_downloader.
Layout: <root>/<sha256(session)[:32]>/<file_id> plus a .json sidecar; one instance per process, disk I/O off the loop; capabilities subclass it via ``file_class``."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WORK_DIR_NAME = "_work"
DATA_NAME_RE = re.compile(r"f_[0-9a-f]{32}")


def new_file_id() -> str:
    return "f_" + secrets.token_hex(16)


class SessionFileStore:
    # The frozen dataclass a sidecar holds (file_id, session, size, created_at, expires_at, ...).
    file_class: type

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int,
        max_file_bytes: int,
        max_session_bytes: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._root = root
        self._ttl = ttl_seconds
        self._max_file_bytes = max_file_bytes
        self._max_session_bytes = max_session_bytes
        self._clock = clock
        self._index: dict[str, Any] = {}
        self._reserved: dict[str, int] = {}

    # --- errors, one per capability ---------------------------------------

    def _not_found(self, file_id: str) -> Exception:
        raise NotImplementedError

    def _delete_failed(self) -> Exception:
        raise NotImplementedError

    # --- paths -------------------------------------------------------------

    def _session_dir(self, session: str) -> Path:
        return self._root / hashlib.sha256(session.encode("utf-8")).hexdigest()[:32]

    def path(self, file: Any) -> Path:
        return self._session_dir(file.session) / file.file_id

    def _meta_path(self, file: Any) -> Path:
        return self._session_dir(file.session) / f"{file.file_id}.json"

    # --- startup -----------------------------------------------------------

    def _prepare_scan(self) -> None:
        """Runs on the scan thread before the sidecars are read."""

    def _accept(self, meta: Path, file: Any) -> bool:
        """Whether a readable sidecar's file is kept; a capability may drop one here."""
        return True

    def _clean_stale(self, found: list[Any]) -> None:
        raise NotImplementedError

    async def load_index(self) -> int:
        """Rebuild the index from sidecars and clean crash leftovers. Returns the number of files loaded."""

        def scan() -> list[Any]:
            self._prepare_scan()
            found: list[Any] = []
            for meta in self._root.glob("*/f_*.json"):
                try:
                    file = self.file_class(**json.loads(meta.read_text("utf-8")))
                except (OSError, ValueError, TypeError):
                    logger.warning("Skipping unreadable sidecar %s", meta)
                    continue
                if self._accept(meta, file):
                    found.append(file)
            self._clean_stale(found)
            return found

        for file in await asyncio.to_thread(scan):
            self._index[file.file_id] = file
        return len(self._index)

    def _delete_unknown_data_files(self, found: list[Any], *, drop_parts: bool) -> None:
        """Delete data files without a sidecar (and, with ``drop_parts``, ``*.part`` files)."""
        known = {file.file_id for file in found}
        for path in self._root.glob("*/f_*"):
            if path.name.endswith(".json") or path.parent.name == WORK_DIR_NAME:
                continue
            if (drop_parts and path.name.endswith(".part")) or (DATA_NAME_RE.fullmatch(path.name) and path.name not in known):
                try:
                    path.unlink()
                except OSError:
                    logger.warning("Could not remove stale file %s", path)

    # --- quota -------------------------------------------------------------

    def _over_quota(self, session: str, size: int) -> bool:
        return self.session_usage(session) + self._reserved.get(session, 0) + size > self._max_session_bytes

    def _release(self, session: str, size: int) -> None:
        """Give back space reserved for a file that is now indexed (or failed)."""
        left = self._reserved.get(session, 0) - size
        if left <= 0:
            self._reserved.pop(session, None)
        else:
            self._reserved[session] = left

    # --- reading -----------------------------------------------------------

    def _valid_id(self, file_id: str) -> bool:
        return True

    def get(self, file_id: str, session: str | None) -> Any:
        """The file, if it exists, has not expired, and ``session`` may see it (None = any)."""
        file = self._index.get(file_id)
        if not self._valid_id(file_id) or file is None or file.expires_at <= self._clock() or (session is not None and file.session != session):
            raise self._not_found(file_id)
        return file

    def list(self, session: str) -> list[Any]:
        now = self._clock()
        files = [f for f in self._index.values() if f.session == session and f.expires_at > now]
        return sorted(files, key=lambda f: f.created_at)

    def session_usage(self, session: str) -> int:
        return sum(f.size for f in self.list(session))

    # --- removal -----------------------------------------------------------

    async def _remove(self, file: Any) -> bool:
        """Remove a file from disk and index. Returns True if successful, False if it failed."""

        def unlink() -> None:
            self.path(file).unlink(missing_ok=True)
            self._meta_path(file).unlink(missing_ok=True)

        try:
            await asyncio.to_thread(unlink)
        except OSError:
            logger.warning("Could not remove file %s", file.file_id)
            return False
        self._index.pop(file.file_id, None)
        return True

    async def delete(self, file_id: str, session: str | None) -> None:
        if not await self._remove(self.get(file_id, session)):
            raise self._delete_failed()

    async def sweep(self) -> int:
        """Delete every expired file. Returns how many were removed."""
        now = self._clock()
        removed = 0
        for file in [f for f in self._index.values() if f.expires_at <= now]:
            if await self._remove(file):
                removed += 1
        return removed

    # --- scratch space -----------------------------------------------------

    async def make_work_dir(self) -> Path:
        """A fresh scratch directory for one job."""
        base = self._root / WORK_DIR_NAME
        await asyncio.to_thread(base.mkdir, parents=True, exist_ok=True)
        return Path(await asyncio.to_thread(tempfile.mkdtemp, dir=base))

    async def remove_work_dir(self, path: Path) -> None:
        await asyncio.to_thread(shutil.rmtree, path, True)
