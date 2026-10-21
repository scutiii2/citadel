import asyncio
import threading
import zipfile
from dataclasses import replace

import pytest

from src.capabilities.video_downloader.utils.errors import DownloaderError, ErrorCode
from src.capabilities.video_downloader.utils.service import Caller


ALICE = Caller('alice')
BOB = Caller('bob')


async def draft(service, count=2):
    package = service.packages.create(ALICE, 'My collection')
    for index in range(count):
        await service.packages.add(ALICE, package.package_id, f'https://example.com/{index}', 'best')
    return service.packages.get(ALICE, package.package_id)


async def test_package_locks_at_start_and_downloads_one_zip(service, fake_extractor):
    package = await draft(service)
    fake_extractor.hold = threading.Event()
    job = service.packages.start(ALICE, package.package_id)
    with pytest.raises(DownloaderError, match='locked'):
        await service.packages.add(ALICE, package.package_id, 'https://example.com/late', 'best')
    with pytest.raises(DownloaderError, match='locked'):
        service.packages.remove(ALICE, package.package_id, package.items[0].item_id)
    with pytest.raises(DownloaderError, match='locked'):
        service.packages.start(ALICE, package.package_id)
    fake_extractor.hold.set()
    result = await service.wait(job)
    assert result['type'] == 'done'
    files = service.list_files(ALICE)
    assert len(files) == 1 and files[0].name == 'My collection.zip'
    assert files[0].kind == 'package'
    with zipfile.ZipFile(service.file_path(files[0])) as archive:
        assert archive.namelist() == ['001-Cat video.mp4', '002-Cat video.mp4']
        assert all(archive.read(name) == fake_extractor.content for name in archive.namelist())
    status = service.packages.get(ALICE, package.package_id)
    assert status.state == 'done' and status.status.file.file_id == files[0].file_id
    assert [item.state for item in status.items] == ['done', 'done']


async def test_packages_are_owned_and_drafts_can_remove_items(service):
    package = await draft(service)
    assert service.packages.list(BOB) == []
    for package_id in [package.package_id, 'missing']:
        with pytest.raises(DownloaderError) as error:
            service.packages.get(BOB, package_id)
        assert error.value.code == ErrorCode.PACKAGE_NOT_FOUND
    service.packages.remove(ALICE, package.package_id, package.items[0].item_id)
    assert len(service.packages.get(ALICE, package.package_id).items) == 1


async def test_empty_or_full_queue_does_not_lock_draft(service, fake_extractor):
    package = service.packages.create(ALICE, 'Empty')
    with pytest.raises(DownloaderError):
        service.packages.start(ALICE, package.package_id)
    assert service.packages.get(ALICE, package.package_id).state == 'draft'
    await service.packages.add(ALICE, package.package_id, 'https://example.com/a', 'best')
    service._jobs._max_per_caller = 1
    fake_extractor.hold = threading.Event()
    busy = await service.start_download(ALICE, 'https://example.com/b', 'best')
    try:
        with pytest.raises(DownloaderError) as error:
            service.packages.start(ALICE, package.package_id)
        assert error.value.code == ErrorCode.QUEUE_FULL
        assert service.packages.get(ALICE, package.package_id).state == 'draft'
    finally:
        fake_extractor.hold.set()
        await service.wait(busy)


async def test_add_rechecks_lock_after_url_validation(service):
    package = await draft(service, 1)
    entered, release = asyncio.Event(), asyncio.Event()
    check = service._policy.check
    async def slow_check(url):
        entered.set()
        await release.wait()
        return await check(url)
    service._policy.check = slow_check
    adding = asyncio.create_task(service.packages.add(ALICE, package.package_id, 'https://example.com/late', 'best'))
    await entered.wait()
    job = service.packages.start(ALICE, package.package_id)
    release.set()
    with pytest.raises(DownloaderError, match='locked'):
        await adding
    await service.wait(job)
    assert len(service.packages.get(ALICE, package.package_id).items) == 1


async def test_partial_package_reports_failed_items(service, fake_extractor):
    package = await draft(service)
    original = fake_extractor.probe
    def probe(url):
        if url.endswith('/0'):
            raise DownloaderError(ErrorCode.EXTRACTOR_FAILED, 'Unavailable media')
        return original(url)
    fake_extractor.probe = probe
    job = service.packages.start(ALICE, package.package_id)
    assert (await service.wait(job))['type'] == 'done'
    status = service.packages.get(ALICE, package.package_id)
    assert [item.state for item in status.items] == ['error', 'done']
    assert status.items[0].error.code == 'extractor_failed'
    with zipfile.ZipFile(service.file_path(service.list_files(ALICE)[0])) as archive:
        assert archive.namelist() == ['002-Cat video.mp4']


async def test_package_enforces_archive_cap_and_cleans_scratch(service, fake_extractor):
    package = await draft(service)
    service._limits = replace(service._limits, max_file_bytes=1500)
    job = service.packages.start(ALICE, package.package_id)
    final = await service.wait(job)
    assert final['type'] == 'error' and final['code'] == 'too_large'
    assert service.list_files(ALICE) == []
    assert list((service.store._root / '_work').iterdir()) == []


async def test_cancelled_package_stays_locked_and_keeps_no_file(service, fake_extractor):
    package = await draft(service)
    fake_extractor.hold = threading.Event()
    job = service.packages.start(ALICE, package.package_id)
    service.cancel_job(ALICE, job.id)
    assert (await service.wait(job))['code'] == 'cancelled'
    assert service.packages.get(ALICE, package.package_id).state == 'error'
    with pytest.raises(DownloaderError, match='locked'):
        await service.packages.add(ALICE, package.package_id, 'https://example.com/new', 'best')
    assert service.list_files(ALICE) == []
