"""Process-owned queue and file store, deliberately outside the reloadable capability.

All mutable state belongs to one background event loop. Offloaded tool threads
submit short operations; yt-dlp itself runs in asyncio's worker executor.
"""
from __future__ import annotations

import asyncio
import logging
import math
import secrets
import threading
from collections.abc import Awaitable, Callable
from dataclasses import fields
from typing import TypeVar
from urllib.parse import urlsplit

from src.config import settings
from src.services.app_config import load_config
from src.utils.catalog import catalog

T = TypeVar("T")
logger = logging.getLogger(__name__)


@catalog
def load_video_settings():
    """Use armory's config loader and the standalone caps/TTL shape, validating bounds."""
    from src.capabilities.video_downloader.utils.config import Limits, Settings
    raw = load_config(settings.video_config_path)
    limits = Limits.from_config(raw.get("limits", {}))
    for field in fields(limits):
        value = getattr(limits, field.name)
        minimum = 0 if field.name == "max_queued_downloads" else 1
        if not math.isfinite(value) or value < minimum:
            raise ValueError(f"{settings.video_config_path}: invalid {field.name}")
    ttl = float(raw.get("file_ttl_hours", 6)) * 3600
    sweep = float(raw.get("sweep_interval_minutes", 10)) * 60
    link = float(raw.get("download_link_minutes", 60)) * 60
    caller_jobs = raw.get("limits", {}).get("max_caller_downloads", 2)
    if any(not math.isfinite(v) or v < 1 for v in (ttl, sweep, link)):
        raise ValueError(f"{settings.video_config_path}: TTLs and sweep interval must be positive")
    if not isinstance(caller_jobs, int) or isinstance(caller_jobs, bool) or caller_jobs < 1:
        raise ValueError(f"{settings.video_config_path}: max_caller_downloads must be a positive integer")
    base_url = settings.video_public_base_url.rstrip("/") or f"http://127.0.0.1:{settings.port}"
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MCP_VIDEO_PUBLIC_BASE_URL must be an http(s) base URL without credentials, query or fragment")
    key = settings.video_signing_key.encode() or secrets.token_bytes(32)
    if not settings.video_signing_key:
        logger.warning("MCP_VIDEO_SIGNING_KEY unset: video links stop working after restart")
    config = Settings(store_dir=settings.video_store_dir, log_dir=settings.video_log_dir,
                      public_base_url=base_url, signing_key=key, limits=limits,
                      file_ttl_seconds=int(ttl), sweep_interval_seconds=int(sweep), download_link_seconds=int(link))
    return config, caller_jobs


@catalog
class VideoRuntime:
    """Serialize service access on a persistent loop; jobs outlive individual tool calls."""
    def __init__(self, config, *, extractor=None, policy=None, max_caller_downloads=2):
        self._config = config
        self._extractor = extractor
        self._policy = policy
        self._max_caller = max_caller_downloads
        self._ready = threading.Event()
        self._error = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="video-downloads", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error:
            self._thread.join()
            raise self._error

    def _run(self):
        from src.capabilities.video_downloader.utils.service import build_service
        from src.services.file_sweeper import run_sweeper
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._service = build_service(self._config, extractor=self._extractor, policy=self._policy)
            self._service._jobs._max_per_caller = self._max_caller
            self._loop.run_until_complete(self._service.store.load_index())
            self._stop = asyncio.Event()
            self._sweeper = self._loop.create_task(run_sweeper(self._service, self._config.sweep_interval_seconds, self._stop))
        except Exception as error:
            self._error = error
            self._loop.close()
            self._ready.set()
            return
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
            self._loop.close()

    def call(self, operation: Callable[..., Awaitable[T]]) -> T:
        if self._closed:
            raise RuntimeError("Video runtime is shutting down")
        return asyncio.run_coroutine_threadsafe(operation(self._service), self._loop).result()

    def close(self):
        if self._closed:
            return
        self._closed = True
        async def shutdown():
            self._stop.set()
            self._service.cancel_all_jobs()
            await self._sweeper
            await asyncio.gather(*tuple(self._service._jobs._tasks), return_exceptions=True)
        asyncio.run_coroutine_threadsafe(shutdown(), self._loop).result()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()


_runtime = None
_lock = threading.Lock()


def get_runtime() -> VideoRuntime:
    global _runtime
    with _lock:
        if _runtime is None:
            config, caller_jobs = load_video_settings()
            _runtime = VideoRuntime(config, max_caller_downloads=caller_jobs)
        return _runtime


def close_runtime():
    global _runtime
    with _lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None
