"""One event loop owns the stored files: uploads, quotas, expiry, and the PDF engine that borrows it.
It is process-wide and lives outside every reloadable capability."""

from __future__ import annotations

import asyncio
import atexit
import logging
import math
import secrets
import threading
from urllib.parse import urlsplit

from src.services import capability_tuning
from src.services.file_sweeper import run_sweeper
from src.services.user_files.service import Settings, build_user_files
from src.services.user_files.store import MB

logger = logging.getLogger(__name__)


class LoopThread:
    """A dedicated event loop on its own thread; `call` runs a coroutine there and waits for it."""

    def __init__(self, name: str) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name=name, daemon=True)
        self.thread.start()
        self.closed = False

    def call(self, coroutine):
        if self.closed:
            coroutine.close()
            raise RuntimeError("Files runtime is closed")
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def close(self) -> None:
        if self.closed:
            return
        try:
            self.call(self.loop.shutdown_asyncgens())
            self.call(self.loop.shutdown_default_executor())
        finally:
            self.closed = True
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()
            self.loop.close()


class FilesRuntime(LoopThread):
    def __init__(self, settings: Settings) -> None:
        super().__init__("user-files")
        self.files = build_user_files(settings)
        self._stop: asyncio.Event | None = None
        try:
            self.call(self._start())
        except BaseException:
            self.close()
            raise

    async def _start(self) -> None:
        await self.files.store.load_index()
        self._stop = asyncio.Event()
        self._sweeper = asyncio.create_task(
            run_sweeper(self.files, self.files.settings.sweep_interval_seconds, self._stop))

    async def _stop_sweeper(self) -> None:
        self._stop.set()
        await self._sweeper

    def close(self) -> None:
        if not self.closed and self._stop is not None:
            self.call(self._stop_sweeper())
        super().close()


def validate_tuning(raw: dict) -> dict:
    """The `Settings` fields of a `files` tuning document; ValueError when it cannot be used."""
    limits = raw.get("limits", {})
    values = {
        "file_ttl_seconds": float(raw.get("file_ttl_hours", 1)) * 3600,
        "sweep_interval_seconds": float(raw.get("sweep_interval_minutes", 10)) * 60,
        "download_link_seconds": float(raw.get("download_link_minutes", 60)) * 60,
        "max_upload_bytes": float(limits.get("max_upload_mb", 15)) * MB,
        "max_audio_upload_bytes": float(limits.get("max_audio_upload_mb", 20)) * MB,
        "max_file_bytes": float(limits.get("max_file_mb", 100)) * MB,
        "max_session_bytes": float(limits.get("max_session_mb", 500)) * MB,
        "max_image_pixels": float(limits.get("max_image_megapixels", 80)) * 1_000_000,
    }
    for name, value in values.items():
        if not math.isfinite(value) or value < 1:
            raise ValueError(f"{name} must be positive and finite")
    return {name: int(value) for name, value in values.items()}


def _config(settings) -> Settings:
    raw = capability_tuning.document(settings.settings_db_path, "files")
    url = settings.pdf_merger_public_base_url or f"http://127.0.0.1:{settings.port}"
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("MCP_PDF_MERGER_PUBLIC_BASE_URL must be an HTTP(S) base URL")
    key = settings.pdf_merger_signing_key
    if not key:
        logger.warning("PDF_MERGER_SIGNING_KEY is unset; file links expire on process restart")
        key = secrets.token_hex(32)
    return Settings(store_dir=settings.files_store_dir, public_base_url=url.rstrip("/"), signing_key=key.encode(),
                    **validate_tuning(raw))


_lock = threading.Lock()
_runtime: FilesRuntime | None = None


def get_runtime(settings) -> FilesRuntime:
    """The process-wide store. Configuration changes require an Armory restart."""
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = FilesRuntime(_config(settings))
    return _runtime


def close_runtime() -> None:
    global _runtime
    with _lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


atexit.register(close_runtime)
