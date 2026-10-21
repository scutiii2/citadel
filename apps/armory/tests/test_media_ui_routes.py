"""Exercise the HTTP boundary against the real owned stores and job loops."""
import asyncio
import threading
from dataclasses import replace

import pikepdf
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src import media_ui_routes
from src.services import capability_registry, pdf_runtime, video_downloads
from src.capabilities.pdf_merger.utils.config import Settings as PdfSettings
from src.capabilities.pdf_merger.utils.service import Caller as PdfCaller
from src.capabilities.video_downloader.utils.config import Settings as VideoSettings
from src.capabilities.video_downloader.utils.policy.url_policy import UrlPolicy
from tests.video_downloader.conftest import FakeExtractor, public_resolver


HEADERS = {"X-Internal-Token": "test", "X-Requester-Uid": "alice"}
OTHER = {**HEADERS, "X-Requester-Uid": "bob"}


def test_video_package_routes_ownership_and_lock(native):
    client, _, runtime, _ = native
    created = client.post('/video/ui/packages', headers=HEADERS, json={'name': 'Mix'})
    assert created.status_code == 200
    package_id = created.json()['package_id']
    path = f'/video/ui/packages/{package_id}'
    assert client.get('/video/ui/packages', headers=OTHER).json() == []
    assert client.get(path, headers=OTHER).status_code == 404
    assert client.get('/video/ui/packages/missing', headers=OTHER).json() == client.get(path, headers=OTHER).json()
    added = client.post(path + '/items', headers=HEADERS, json={'url': 'https://example.com/a', 'preset': 'best'})
    assert len(added.json()['items']) == 1
    started = client.post(path + '/start', headers=HEADERS, json={})
    assert started.status_code == 200
    late = client.post(path + '/items', headers=HEADERS, json={'url': 'https://example.com/b', 'preset': 'best'})
    assert late.status_code == 409 and late.json()['error']['code'] == 'package_locked'
    async def wait(service):
        from src.capabilities.video_downloader.utils.service import Caller
        return await service.wait(service.get_job(Caller('uid:alice'), started.json()['job_id']))
    runtime.call(wait)
    status = client.get(path, headers=HEADERS).json()
    assert status['state'] == 'done' and status['status']['file']['kind'] == 'package'


@pytest.fixture
def native(tmp_path, monkeypatch):
    from src.capabilities.video_downloader import domain
    pdf = pdf_runtime.Runtime(PdfSettings(store_dir=tmp_path / "pdf", signing_key=b"p" * 32))
    extractor = FakeExtractor()
    video = video_downloads.VideoRuntime(VideoSettings(store_dir=tmp_path / "video", signing_key=b"v" * 32),
                                         extractor=extractor, policy=UrlPolicy(public_resolver))
    monkeypatch.setattr(pdf_runtime, "get_runtime", lambda _: pdf)
    monkeypatch.setattr(video_downloads, "get_runtime", lambda: video)
    monkeypatch.setattr(domain.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(media_ui_routes, "settings", replace(media_ui_routes.settings, internal_api_token="test", host="127.0.0.1"))
    monkeypatch.setattr(capability_registry, "is_enabled", lambda _: True)
    app = Starlette()
    media_ui_routes.install_media_ui_routes(app)
    try:
        with TestClient(app) as client:
            yield client, pdf, video, extractor
    finally:
        pdf.close()
        video.close()


@pytest.mark.parametrize("kind", ["pdf", "video"])
def test_auth_identity_and_disabled_gate(native, monkeypatch, kind):
    client, *_ = native
    path = f"/{kind}/ui/files"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Internal-Token": "test"}).status_code == 400
    monkeypatch.setattr(capability_registry, "is_enabled", lambda _: False)
    assert client.get(path, headers=HEADERS).status_code == 503
    monkeypatch.setattr(media_ui_routes, "settings", replace(media_ui_routes.settings, internal_api_token=""))
    assert client.get(path, headers=HEADERS).status_code == 401


def upload_pdf(runtime, tmp_path):
    path = tmp_path / "source.pdf"
    with pikepdf.new() as pdf:
        pdf.add_blank_page(page_size=(100, 200))
        pdf.save(path)
    content = path.read_bytes()
    async def operation():
        async def chunks():
            yield content
        return await runtime.service.upload(PdfCaller("alice"), "source.pdf", chunks())
    return runtime.call(operation())


def test_pdf_owned_files_content_merge_and_delete(native, tmp_path):
    client, pdf, *_ = native
    file = upload_pdf(pdf, tmp_path)
    listed = client.get("/pdf/ui/files", headers=HEADERS).json()
    assert listed[0]["file_id"] == file.file_id
    assert "/pdf/files/" in listed[0]["download_url"]
    path = f"/pdf/ui/files/{file.file_id}"
    content = client.get(path + "/content", headers=HEADERS)
    assert content.content.startswith(b"%PDF-")
    assert content.headers["content-security-policy"] == "sandbox"
    assert client.get("/pdf/ui/files", headers=OTHER).json() == []
    for method, suffix in (("GET", "/content"), ("DELETE", "")):
        hidden = client.request(method, path + suffix, headers=OTHER)
        missing = client.request(method, "/pdf/ui/files/missing" + suffix, headers=OTHER)
        assert hidden.status_code == missing.status_code == 404
        assert hidden.json() == missing.json()
    job_id = client.post("/pdf/ui/merge", headers=HEADERS,
                         json={"segments": [{"file_id": file.file_id}]}).json()["job_id"]
    async def wait():
        return await pdf.service._jobs.wait(pdf.service.get_job(PdfCaller("alice"), job_id))
    pdf.call(wait())
    status = client.get(f"/pdf/ui/jobs/{job_id}", headers=HEADERS).json()
    assert status["state"] == "done" and status["result"]["pages"] == 1
    assert client.get(f"/pdf/ui/jobs/{job_id}", headers=OTHER).status_code == 404
    assert client.post(f"/pdf/ui/jobs/{job_id}/cancel", headers=OTHER).status_code == 404
    assert client.delete(path, headers=HEADERS).json() == {"ok": True}
    assert client.get(path + "/content", headers=HEADERS).status_code == 404


def test_pdf_cancel_preserves_queue_status(native):
    client, pdf, *_ = native
    async def submit():
        async def work(progress, cancel):
            while not cancel.is_set():
                await asyncio.sleep(0.001)
            from src.services.pdf_errors import MergerError, ErrorCode
            raise MergerError(ErrorCode.MERGE_TIMEOUT, "Stopped")
        return pdf.service._jobs.submit("alice", 1, work).id
    job_id = pdf.call(submit())
    assert client.post(f"/pdf/ui/jobs/{job_id}/cancel", headers=HEADERS).json() == {"ok": True}
    async def wait():
        await pdf.service._jobs.wait(pdf.service.get_job(PdfCaller("alice"), job_id))
    pdf.call(wait())
    status = client.get(f"/pdf/ui/jobs/{job_id}", headers=HEADERS).json()
    assert status["state"] == "error" and status["error"]["code"] == "merge_timeout"


def test_photos_cross_http_boundary_without_ffmpeg(native, monkeypatch):
    from src.capabilities.video_downloader import domain
    from src.capabilities.video_downloader.utils.service import Caller
    client, _, video, extractor = native
    monkeypatch.setattr(domain.shutil, "which", lambda _: None)
    extractor.info = replace(extractor.info, photo_count=3, duration=None, formats=[])
    extractor.suffix = ".zip"
    probe = client.post("/video/ui/probe", headers=HEADERS, json={"url": "https://example.com/post"})
    assert probe.status_code == 200
    assert probe.json()["photo_count"] == 3
    started = client.post("/video/ui/downloads", headers=HEADERS, json={"url": "https://example.com/post", "preset": "photos"})
    assert started.status_code == 200
    job_id = started.json()["job_id"]
    async def wait(service):
        return await service.wait(service.get_job(Caller("uid:alice"), job_id))
    assert video.call(wait)["type"] == "done"
    status = client.get(f"/video/ui/jobs/{job_id}", headers=HEADERS).json()
    assert status["file"]["mime"] == "application/zip"
    assert status["file"]["kind"] == "photo"
    assert client.get("/video/ui/files", headers=OTHER).json() == []


def test_video_policy_download_status_delete_and_cancel(native):
    from src.capabilities.video_downloader.utils.service import Caller
    client, _, video, extractor = native
    assert client.post("/video/ui/probe", headers=HEADERS, json={"url": "http://127.0.0.1/private"}).status_code == 403
    assert client.post("/video/ui/downloads", headers=HEADERS, json={"url": "http://127.0.0.1/private", "preset": "720p"}).status_code == 403
    assert client.post("/video/ui/probe", headers=HEADERS, json={"url": "https://example.com/v"}).json()["title"] == "Cat video"
    job_id = client.post("/video/ui/downloads", headers=HEADERS,
                         json={"url": "https://example.com/v", "preset": "720p"}).json()["job_id"]
    async def wait(service):
        await service.wait(service.get_job(Caller("uid:alice"), job_id))
    video.call(wait)
    status = client.get(f"/video/ui/jobs/{job_id}", headers=HEADERS).json()
    assert status["state"] == "done" and status["percent"] == 100
    assert client.get("/video/ui/files", headers=OTHER).json() == []
    assert client.get(f"/video/ui/jobs/{job_id}", headers=OTHER).status_code == 404
    assert client.post(f"/video/ui/jobs/{job_id}/cancel", headers=OTHER).status_code == 404
    file_id = status["file"]["file_id"]
    assert client.get("/video/ui/files", headers=HEADERS).json()[0]["file_id"] == file_id
    assert client.delete(f"/video/ui/files/{file_id}", headers=OTHER).json() == client.delete("/video/ui/files/missing", headers=OTHER).json()
    assert client.delete(f"/video/ui/files/{file_id}", headers=HEADERS).json() == {"ok": True}
    extractor.hold = threading.Event()
    job_id = client.post("/video/ui/downloads", headers=HEADERS,
                         json={"url": "https://example.com/v", "preset": "720p"}).json()["job_id"]
    assert client.post(f"/video/ui/jobs/{job_id}/cancel", headers=HEADERS).json() == {"ok": True}
    video.call(wait)
    status = client.get(f"/video/ui/jobs/{job_id}", headers=HEADERS).json()
    assert status["state"] == "error" and status["error"]["code"] == "cancelled"


@pytest.mark.parametrize("path", ["/pdf/ui/merge", "/video/ui/probe", "/video/ui/downloads"])
def test_bad_json_and_validation(native, path):
    client, *_ = native
    assert client.post(path, headers=HEADERS, content="{").status_code == 422
    assert client.post(path, headers=HEADERS, json={}).status_code == 422


def test_unexpected_error_is_sanitized(native, monkeypatch):
    client, *_ = native
    def fail(*_):
        raise OSError("private storage location")
    monkeypatch.setattr(media_ui_routes, "_pdf_operation", fail)
    response = client.get("/pdf/ui/files", headers=HEADERS)
    assert response.status_code == 503 and "private" not in response.text
