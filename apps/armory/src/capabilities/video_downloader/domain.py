"""Typed, protocol-independent operations on the process-owned download runtime."""
from __future__ import annotations

import logging
import shutil

from .contract import DownloadStarted, ListFilesResult, ProbeToolResult, StatusToolResult
from .utils.errors import DownloaderError, ErrorCode
from .utils.service import Caller
from src.config import settings
from src.services.identity_context import current_uid, current_username
from src.services.internal_token import is_exposed_without_token
from src.services.untrusted import fenced_and_capped
from src.services.video_downloads import get_runtime

logger = logging.getLogger(__name__)


def caller() -> Caller:
    if is_exposed_without_token(settings.host, settings.internal_api_token):
        raise ValueError("Video downloads require INTERNAL_API_TOKEN when armory is exposed beyond loopback.")
    uid = current_uid().strip()
    if not uid:
        raise ValueError("Video downloads require an authenticated account identity.")
    # Usernames can change; only the stable uid owns files, jobs and quotas.
    return Caller(session="uid:" + uid)


def _require_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise DownloaderError(ErrorCode.FFMPEG_MISSING, "FFmpeg is missing. Install FFmpeg on armory's PATH, then try again.")


def _text(value: str) -> str:
    return fenced_and_capped(value, source="video metadata", max_bytes=4096)


def probe(url: str) -> ProbeToolResult:
    caller()
    async def operation(service):
        result = await service.probe(url)
        if not result.photo_count:
            _require_ffmpeg()
        return ProbeToolResult(**result.model_dump(exclude={"title", "uploader"}),
                               title=_text(result.title), uploader=_text(result.uploader) if result.uploader else None,
                               message="Choose an unblocked preset, then start a download.")
    return get_runtime().call(operation)


def download(url: str, preset: str = "best") -> DownloadStarted:
    owner = caller()
    if preset != "photos":
        _require_ffmpeg()
    username = current_username()
    async def operation(service):
        job = await service.start_download(owner, url, preset)
        logger.info("Queued video job %s for account %s (%s)", job.id, owner.session, username)
        return DownloadStarted(job_id=job.id, message="Download queued. Poll status with this job_id.")
    return get_runtime().call(operation)


def status(job_id: str) -> StatusToolResult:
    owner = caller()
    async def operation(service):
        result = service.job_status(owner, job_id)
        if result.file:
            result.file.name = _text(result.file.name)
        return StatusToolResult(**result.model_dump(), message=f"Download state: {result.state}.")
    return get_runtime().call(operation)


def list_files() -> ListFilesResult:
    owner = caller()
    async def operation(service):
        files = [service.file_info(file) for file in service.list_files(owner)]
        for file in files:
            file.name = _text(file.name)
        return ListFilesResult(files=files, message=f"{len(files)} file(s), with fresh download links.")
    return get_runtime().call(operation)
