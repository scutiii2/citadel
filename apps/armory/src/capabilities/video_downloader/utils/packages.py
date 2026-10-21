"""Owned draft packages. All mutations run on the download runtime's event loop.

One package is one bounded queue job; members run sequentially under that slot.
Drafts and job history are process-local, like the existing queue. Only ZIPs persist.
"""
from __future__ import annotations

import asyncio
import secrets
import time
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.utils.catalog import catalog
from .errors import DownloaderError, ErrorCode
from .extractor.presets import get_preset
from .models import ErrorInfo, PackageInfo, PackageItem
from .store.names import safe_filename

if TYPE_CHECKING:
    from .service import Caller, DownloadService


@dataclass
class _Package:
    owner: str
    created_at: float
    info: PackageInfo


@catalog
class PackageManager:
    """Account-scoped editable drafts with an atomic, permanent lock at queue admission."""

    def __init__(self, service: DownloadService):
        self._service = service
        self._packages: dict[str, _Package] = {}

    def _owned(self, caller: Caller, package_id: str) -> _Package:
        package = self._packages.get(package_id)
        if package is None or package.owner != caller.session:
            raise DownloaderError(ErrorCode.PACKAGE_NOT_FOUND, 'That package is not available.')
        return package

    def _draft(self, caller: Caller, package_id: str) -> PackageInfo:
        info = self._owned(caller, package_id).info
        if info.job_id is not None:
            raise DownloaderError(ErrorCode.PACKAGE_LOCKED, 'This package is locked because its download has started. Create another group to add media.')
        return info

    def create(self, caller: Caller, name: str) -> PackageInfo:
        name = name.strip()
        if not name or len(name) > 150:
            raise DownloaderError(ErrorCode.INVALID_REQUEST, 'Give the group a name of 1 to 150 characters.')
        if sum(p.owner == caller.session for p in self._packages.values()) >= 20:
            raise DownloaderError(ErrorCode.LIMIT_EXCEEDED, 'You have too many groups. Wait for older groups to expire.')
        info = PackageInfo(package_id='p_' + secrets.token_hex(12), name=name)
        self._packages[info.package_id] = _Package(caller.session, time.time(), info)
        return info.model_copy(deep=True)

    def get(self, caller: Caller, package_id: str) -> PackageInfo:
        result = self._owned(caller, package_id).info.model_copy(deep=True)
        if result.job_id:
            result.status = self._service.job_status(caller, result.job_id)
            result.state = result.status.state
        return result

    def list(self, caller: Caller) -> list[PackageInfo]:
        return [self.get(caller, key) for key, p in self._packages.items() if p.owner == caller.session]

    async def add(self, caller: Caller, package_id: str, url: str, preset_id: str) -> PackageInfo:
        self._draft(caller, package_id)
        preset = get_preset(preset_id)
        clean = await self._service._policy.check(url)
        # URL checks yield. A concurrent start must win over this in-flight add.
        info = self._draft(caller, package_id)
        if len(info.items) >= 50:
            raise DownloaderError(ErrorCode.LIMIT_EXCEEDED, 'A group can contain at most 50 media links.')
        info.items.append(PackageItem(item_id='i_' + secrets.token_hex(12), url=clean, preset=preset.id))
        return self.get(caller, package_id)

    def remove(self, caller: Caller, package_id: str, item_id: str) -> PackageInfo:
        info = self._draft(caller, package_id)
        if not any(item.item_id == item_id for item in info.items):
            raise DownloaderError(ErrorCode.INVALID_REQUEST, 'That media item is not available.')
        info.items = [item for item in info.items if item.item_id != item_id]
        return self.get(caller, package_id)

    def start(self, caller: Caller, package_id: str):
        info = self._draft(caller, package_id)
        if not info.items:
            raise DownloaderError(ErrorCode.INVALID_REQUEST, 'Add media to the group before starting its download.')
        async def work(emit, cancel):
            return await self._run(caller.session, info, emit, cancel)
        # No await between submission and locking. Queue refusal leaves the draft editable.
        job = self._service._jobs.submit(caller.session, work)
        info.job_id = job.id
        info.state = 'queued'
        return job

    async def _run(self, session, info, emit, cancel):
        service = self._service
        work = await service.store.make_work_dir()
        archive_path = work / 'package.zip'
        total_bytes = 0
        completed = 0
        try:
            with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_STORED) as archive:
                for index, item in enumerate(info.items):
                    self._check_cancel(cancel)
                    item.state = 'downloading'
                    item_work = await service.store.make_work_dir()
                    def progress(event):
                        percent = event.get('percent') or 0
                        emit({'type': 'progress', 'percent': (index + percent / 100) / len(info.items) * 100,
                              'speed': event.get('speed'), 'eta': None})
                    try:
                        media, downloaded = await service._download_to_work(
                            session, item.url, get_preset(item.preset), item_work, progress, cancel)
                        item.title = media.title
                        size = (await asyncio.to_thread(downloaded.path.stat)).st_size
                        total_bytes += size
                        if total_bytes > service._limits.max_file_bytes:
                            raise DownloaderError(ErrorCode.TOO_LARGE, 'The package exceeds the configured file size limit. Use a smaller group.')
                        name = f'{index + 1:03d}-' + safe_filename(media.title, 'media') + downloaded.path.suffix
                        await asyncio.to_thread(self._append, archive, downloaded.path, name, cancel)
                        item.state = 'done'
                        completed += 1
                    except DownloaderError as error:
                        item.state = 'error'
                        item.error = ErrorInfo(code=str(error.code), message=error.message)
                        if error.code in {ErrorCode.CANCELLED, ErrorCode.TOO_LARGE, ErrorCode.LIMIT_EXCEEDED}:
                            raise
                    finally:
                        await service.store.remove_work_dir(item_work)
                    emit({'type': 'progress', 'percent': (index + 1) / len(info.items) * 100, 'speed': None, 'eta': None})
            self._check_cancel(cancel)
            if not completed:
                raise DownloaderError(ErrorCode.EXTRACTOR_FAILED, 'None of the media could be downloaded. Create a new group with working links.')
            emit({'type': 'processing'})
            stored = await service.store.commit_file(session, archive_path,
                name=safe_filename(info.name, 'package') + '.zip', mime='application/zip', kind='package', duration=None)
            return {'file_id': stored.file_id, 'file': service.file_info(stored).model_dump(mode='json')}
        finally:
            await service.store.remove_work_dir(work)

    @staticmethod
    def _check_cancel(cancel):
        if cancel.is_set():
            raise DownloaderError(ErrorCode.CANCELLED, 'The download was cancelled.')

    def _append(self, archive, source, name, cancel):
        # Chunked writes keep cancellation responsive even for a large local file.
        with source.open('rb') as src, archive.open(name, 'w', force_zip64=True) as dst:
            while chunk := src.read(1024 * 1024):
                self._check_cancel(cancel)
                dst.write(chunk)

    def prune(self, older_than: float):
        stale = [key for key, package in self._packages.items() if package.created_at < older_than
                 and (not package.info.job_id or package.info.job_id not in self._service._jobs._jobs)]
        for key in stale:
            del self._packages[key]
