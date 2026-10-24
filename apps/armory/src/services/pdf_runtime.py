"""One event loop owns PDF jobs, quotas and cleanup across capability reloads.

The owner lives outside the reloadable capability to prevent duplicate sweepers
and indexes on an offline/online cycle. Engine imports remain lazy.
"""
from __future__ import annotations

import atexit
import asyncio
import logging
import math
import secrets
import threading
from dataclasses import asdict, replace
from urllib.parse import urlsplit

from src.services.app_config import load_config

logger = logging.getLogger(__name__)


class Runtime:
    """Keep mutable PDF state on a dedicated loop, leaving blocking I/O offloaded."""

    def __init__(self, config):
        self.config = config
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="pdf-merger", daemon=True)
        self.thread.start()
        self.closed = False
        try:
            self.call(self._initialize())
        except BaseException:
            self.close()
            raise

    async def _initialize(self):
        from src.capabilities.pdf_merger.utils.service import build_service
        from src.services.file_sweeper import run_sweeper

        self.service = build_service(self.config)
        await self.service.store.load_index()
        self.stop = asyncio.Event()
        self.sweeper = asyncio.create_task(run_sweeper(self.service, self.config.sweep_interval_seconds, self.stop))

    def call(self, coroutine):
        if self.closed:
            coroutine.close()
            raise RuntimeError("PDF runtime is closed")
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

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
            self.call(self._shutdown())
            self.call(self.loop.shutdown_asyncgens())
            self.call(self.loop.shutdown_default_executor())
        finally:
            self.closed = True
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()
            self.loop.close()


_lock = threading.Lock()
_runtime = None


def _engine_config(settings):
    from src.capabilities.pdf_merger.utils.config import Limits, Settings

    raw = load_config(settings.pdf_merger_config_path)
    limits = Limits.from_config(raw.get("limits", {}))
    for name, value in asdict(limits).items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
    wait = float(raw.get("mcp_wait_seconds", 100))
    if not 0 < wait <= 100:
        raise ValueError("mcp_wait_seconds must be between 0 and 100")
    ttl = float(raw.get("file_ttl_hours", 6)) * 3600
    sweep = float(raw.get("sweep_interval_minutes", 10)) * 60
    link = float(raw.get("download_link_minutes", 60)) * 60
    if any(not math.isfinite(v) or v < 1 for v in (ttl, sweep, link)):
        raise ValueError("PDF expiry and sweep intervals must be positive and finite")
    url = settings.pdf_merger_public_base_url or f"http://127.0.0.1:{settings.port}"
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("MCP_PDF_MERGER_PUBLIC_BASE_URL must be an HTTP(S) base URL")
    key = settings.pdf_merger_signing_key
    if not key:
        logger.warning("PDF_MERGER_SIGNING_KEY is unset; PDF links expire on process restart")
        key = secrets.token_hex(32)
    return Settings(
        store_dir=settings.pdf_merger_store_dir, public_base_url=url.rstrip("/"), signing_key=key.encode(),
        file_ttl_seconds=int(ttl), sweep_interval_seconds=int(sweep), download_link_seconds=int(link),
        mcp_wait_seconds=wait, limits=replace(limits, job_timeout_seconds=min(limits.job_timeout_seconds, wait)),
    )


def get_runtime(settings):
    """Lazy process-wide PDF engine. Configuration changes require an Armory restart."""
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = Runtime(_engine_config(settings))
    return _runtime


def close_runtime():
    global _runtime
    with _lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


atexit.register(close_runtime)
