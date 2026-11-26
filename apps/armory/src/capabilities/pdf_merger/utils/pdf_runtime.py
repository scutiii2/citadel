"""One event loop owns PDF jobs, quotas and cleanup across capability reloads.
It lives outside the reloadable capability to avoid duplicate sweepers; engine imports stay lazy."""
from __future__ import annotations

import atexit
import asyncio
import logging
import math
import threading
from dataclasses import asdict, replace

from src.services import capability_tuning
from src.services.user_files import runtime as files_runtime
from src.services.user_files.runtime import FilesRuntime, LoopThread

logger = logging.getLogger(__name__)


class Runtime:
    """Mutable PDF state on one loop: the shared files loop in Armory, a private one when built alone (tests)."""

    def __init__(self, config, shared: FilesRuntime | None = None):
        self.config = config
        self._shared = shared
        self._own = None if shared else LoopThread("pdf-merger")
        self._thread = shared or self._own
        self.closed = False
        try:
            self.call(self._initialize())
        except BaseException:
            self.close()
            raise

    async def _initialize(self):
        from src.capabilities.pdf_merger.utils.service import build_service
        from src.services.file_sweeper import run_sweeper

        self.service = build_service(self.config, self._shared.files if self._shared else None)
        if self._shared is None:
            await self.service.store.load_index()
        self.stop = asyncio.Event()
        # Also forgets old merge jobs; sweeping files twice on one loop is harmless.
        self.sweeper = asyncio.create_task(run_sweeper(self.service, self.config.sweep_interval_seconds, self.stop))

    def call(self, coroutine):
        if self.closed:
            coroutine.close()
            raise RuntimeError("PDF runtime is closed")
        return self._thread.call(coroutine)

    async def _shutdown(self):
        if hasattr(self, "stop"):
            self.stop.set()
            await self.sweeper
        if hasattr(self, "service"):
            jobs = self.service._jobs
            for job in jobs._jobs.values():
                job.cancel()
            if jobs._tasks:
                await asyncio.gather(*jobs._tasks, return_exceptions=True)

    def close(self):
        if self.closed:
            return
        try:
            if not self._thread.closed:
                self.call(self._shutdown())
        finally:
            self.closed = True
            if self._own is not None:
                self._own.close()


_lock = threading.Lock()
_runtime = None


def validate_tuning(raw):
    """Refuse an unusable merge-limits document (ValueError); the Limits page uses it before saving."""
    from src.capabilities.pdf_merger.utils.config import Limits

    limits = Limits.from_config(raw.get("limits", {}))
    for name, value in asdict(limits).items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    wait = float(raw.get("mcp_wait_seconds", 100))
    if not 0 < wait <= 100:
        raise ValueError("mcp_wait_seconds must be between 0 and 100")
    return limits, wait


def _engine_config(settings, files):
    from src.capabilities.pdf_merger.utils.config import Settings

    limits, wait = validate_tuning(capability_tuning.document(settings.settings_db_path, "pdf_merger"))
    return Settings(
        store_dir=files.store_dir, public_base_url=files.public_base_url, signing_key=files.signing_key,
        file_ttl_seconds=files.file_ttl_seconds, sweep_interval_seconds=files.sweep_interval_seconds,
        download_link_seconds=files.download_link_seconds, mcp_wait_seconds=wait,
        limits=replace(limits, job_timeout_seconds=min(limits.job_timeout_seconds, wait)),
    )


def get_runtime(settings):
    """Lazy process-wide PDF engine on the shared files loop. Configuration changes require an Armory restart."""
    global _runtime
    with _lock:
        if _runtime is None:
            shared = files_runtime.get_runtime(settings)
            _runtime = Runtime(_engine_config(settings, shared.files.settings), shared)
    return _runtime


def close_runtime():
    global _runtime
    with _lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


atexit.register(close_runtime)
