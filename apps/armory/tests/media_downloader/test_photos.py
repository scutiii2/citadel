"""Photo extraction and bounded downloads use synthetic HTTP responses only."""
import io
import json
import threading
import zipfile

import pytest
import requests
from PIL import Image

from src.capabilities.media_downloader.utils.errors import DownloaderError, ErrorCode
from src.capabilities.media_downloader.utils.extractor.photos import PhotoExtractor
from src.capabilities.media_downloader.utils.extractor.options import available_presets
from src.capabilities.media_downloader.utils.extractor.presets import get_preset


def image_bytes(fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "orange").save(output, fmt)
    return output.getvalue()


class MemoryAdapter(requests.adapters.BaseAdapter):
    def __init__(self, routes):
        self.routes = routes
        self.seen = []
        self.omit_length = False
        self.redirects = {}

    def send(self, request, **kwargs):
        self.seen.append(request.url)
        body, mime = self.routes[request.url]
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response.request = request
        response.headers["Content-Type"] = mime
        if request.url in self.redirects:
            response.status_code = 302
            response.headers["Location"] = self.redirects[request.url]
        if not self.omit_length:
            response.headers["Content-Length"] = str(len(body))
        response.raw = io.BytesIO(body)
        return response

    def close(self):
        pass


@pytest.fixture
def photo_engine():
    from src.capabilities.media_downloader.utils.extractor.photos import PhotoSession
    adapter = MemoryAdapter({})

    def session():
        result = PhotoSession()
        result.mount("https://", adapter)
        return result

    return PhotoExtractor(session_factory=session), adapter


def download(engine, url, tmp_path, **overrides):
    options = dict(max_bytes=100_000, max_duration_seconds=60, on_progress=lambda p: None, cancel=threading.Event())
    options.update(overrides)
    return engine.download(url, get_preset("photos"), tmp_path, **options)


def test_extensionless_image_is_detected_and_downloaded_in_original_format(photo_engine, tmp_path):
    engine, adapter = photo_engine
    url = "https://images.example/asset?id=42"
    content = image_bytes()
    adapter.routes[url] = (content, "image/png")
    info = engine.probe(url)
    assert info.photo_count == 1
    assert [p.id for p in available_presets(info)] == ["photos"]
    result = download(engine, url, tmp_path)
    assert result.path.suffix == ".png"
    assert result.path.read_bytes() == content


def test_non_image_link_can_fall_back_to_video(photo_engine):
    engine, adapter = photo_engine
    adapter.routes["https://example.com/watch"] = (b"<html>video</html>", "text/html")
    assert engine.probe("https://example.com/watch") is None


def test_tiktok_carousel_extracts_all_photos_and_preserves_order(photo_engine, tmp_path):
    engine, adapter = photo_engine
    urls = ["https://cdn.example/first.png", "https://cdn.example/second.png"]
    post = {"id": "1234567890", "desc": "Holiday", "createTime": "1700000000", "author": {"uniqueId": "alice"},
            "imagePost": {"images": [{"imageURL": {"urlList": [u]}, "imageWidth": 2, "imageHeight": 2} for u in urls]}}
    data = {"__DEFAULT_SCOPE__": {"webapp.video-detail": {"statusCode": 0, "itemInfo": {"itemStruct": post}}}}
    html = '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">' + json.dumps(data) + '</script>'
    adapter.routes["https://www.tiktok.com/@alice/video/1234567890"] = (html.encode(), "text/html")
    for url in urls:
        adapter.routes[url] = (image_bytes(), "image/png")
    url = "https://www.tiktok.com/@alice/photo/1234567890"
    info = engine.probe(url)
    assert info.photo_count == 2
    assert info.title == "Holiday"
    result = download(engine, url, tmp_path)
    assert result.path.suffix == ".zip"
    with zipfile.ZipFile(result.path) as archive:
        assert archive.namelist() == ["001.png", "002.png"]
        assert all(archive.read(n) == image_bytes() for n in archive.namelist())


def test_photos_obey_byte_cap_even_without_content_length(photo_engine, tmp_path):
    engine, adapter = photo_engine
    url = "https://cdn.example/photo.png"
    adapter.routes[url] = (image_bytes(), "image/png")
    adapter.omit_length = True
    with pytest.raises(DownloaderError) as error:
        download(engine, url, tmp_path, max_bytes=10)
    assert error.value.code == ErrorCode.TOO_LARGE


def test_private_image_host_is_blocked_at_connection_time():
    with pytest.raises(DownloaderError) as error:
        PhotoExtractor().probe("http://127.0.0.1/photo.png")
    assert error.value.code == ErrorCode.BLOCKED_HOST


def test_photo_redirect_to_private_address_is_blocked(photo_engine):
    engine, adapter = photo_engine
    url = "https://cdn.example/photo.png"
    adapter.routes[url] = (b"redirect", "text/plain")
    adapter.redirects[url] = "http://127.0.0.1/photo.png"
    with pytest.raises(DownloaderError) as error:
        engine.probe(url)
    assert error.value.code == ErrorCode.BLOCKED_HOST


def test_social_post_cannot_download_a_private_asset(photo_engine, monkeypatch, tmp_path):
    from gallery_dl.extractor.pinterest import PinterestAPI
    engine, _ = photo_engine
    monkeypatch.setattr(PinterestAPI, "pin", lambda self, pin_id: {
        "id": pin_id, "images": {"orig": {"url": "http://127.0.0.1/photo.png"}},
    })
    with pytest.raises(DownloaderError) as error:
        download(engine, "https://www.pinterest.com/pin/123456/", tmp_path)
    assert error.value.code == ErrorCode.BLOCKED_HOST


def test_metadata_is_bounded_before_gallery_parses_it(photo_engine, monkeypatch):
    from src.capabilities.media_downloader.utils.extractor import photos
    engine, adapter = photo_engine
    monkeypatch.setattr(photos, "MAX_METADATA_BYTES", 16)
    adapter.routes["https://www.tiktok.com/@alice/video/1234567890"] = (b"x" * 32, "text/html")
    with pytest.raises(DownloaderError):
        engine.probe("https://www.tiktok.com/@alice/photo/1234567890")


def test_pinterest_pin_uses_original_image(photo_engine, monkeypatch):
    from gallery_dl.extractor.pinterest import PinterestAPI
    engine, adapter = photo_engine
    url = "https://i.pinimg.com/originals/photo.jpg"
    monkeypatch.setattr(PinterestAPI, "pin", lambda self, pin_id: {
        "id": pin_id, "title": "Garden", "images": {"orig": {"url": url, "width": 2, "height": 2}},
    })
    assert engine.probe("https://www.pinterest.com/pin/123456/").photo_count == 1
    assert adapter.seen == []  # CDN bytes are fetched only when downloading.


def test_large_carousel_downloads_every_photo(photo_engine, monkeypatch, tmp_path):
    from gallery_dl.extractor.pinterest import PinterestAPI
    engine, adapter = photo_engine
    def pin(self, pin_id):
        return {"id": pin_id, "title": "Album", "carousel_data": {"carousel_slots": [
            {"id": str(i), "images": {"orig": {"url": f"https://cdn.example/orig/{i}.png"}}} for i in range(40)
        ]}}
    monkeypatch.setattr(PinterestAPI, "pin", pin)
    for i in range(40):
        adapter.routes[f"https://cdn.example/originals/{i}.png"] = (image_bytes(), "image/png")
    result = download(engine, "https://www.pinterest.com/pin/123456/", tmp_path)
    with zipfile.ZipFile(result.path) as archive:
        assert len(archive.namelist()) == 40


def test_instagram_reels_fall_back_to_video(photo_engine):
    engine, adapter = photo_engine
    assert engine.probe("https://www.instagram.com/reel/ABC/") is None
    assert adapter.seen == []


def test_video_fallback_when_photo_inspection_cannot_fetch_the_page():
    from unittest.mock import Mock
    from src.capabilities.media_downloader.utils.extractor.media import MediaExtractor
    engine = MediaExtractor()
    engine._photos = Mock()
    engine._video = Mock()
    engine._photos.probe.side_effect = DownloaderError(ErrorCode.EXTRACTOR_FAILED, "HTTP inspection failed")
    expected = engine._video.probe.return_value
    assert engine.probe("https://www.youtube.com/watch?v=test") is expected


def test_blocked_photo_inspection_never_falls_back_to_another_engine():
    from unittest.mock import Mock
    from src.capabilities.media_downloader.utils.extractor.media import MediaExtractor
    engine = MediaExtractor()
    engine._photos = Mock()
    engine._video = Mock()
    engine._photos.probe.side_effect = DownloaderError(ErrorCode.BLOCKED_HOST, "Blocked")
    with pytest.raises(DownloaderError):
        engine.probe("https://example.com/watch")
    engine._video.probe.assert_not_called()


def test_social_video_can_use_ytdlp_when_gallery_requires_login():
    from unittest.mock import Mock
    from src.capabilities.media_downloader.utils.extractor.media import MediaExtractor
    engine = MediaExtractor()
    engine._photos = Mock()
    engine._video = Mock()
    engine._photos.probe.side_effect = DownloaderError(ErrorCode.LOGIN_REQUIRED, "Gallery requires login")
    assert engine.probe("https://www.instagram.com/p/ABC/") is engine._video.probe.return_value


def test_explicit_tiktok_photo_failure_is_not_retried_as_video():
    from unittest.mock import Mock
    from src.capabilities.media_downloader.utils.extractor.media import MediaExtractor
    engine = MediaExtractor()
    engine._photos = Mock()
    engine._video = Mock()
    engine._photos.probe.side_effect = DownloaderError(ErrorCode.EXTRACTOR_FAILED, "Photo not available")
    with pytest.raises(DownloaderError):
        engine.probe("https://www.tiktok.com/@alice/photo/1234567890")
    engine._video.probe.assert_not_called()


def test_instagram_carousel_excludes_video_and_thumbnail(photo_engine, monkeypatch):
    from gallery_dl.extractor.instagram import InstagramAPI
    engine, _ = photo_engine
    def item(pk, video=False):
        return {"pk": str(pk), "image_versions2": {"candidates": [{"url": f"https://cdn.example/{pk}.jpg", "width": 2, "height": 2}]},
                **({"video_versions": [{"url": "https://cdn.example/video.mp4"}]} if video else {})}
    monkeypatch.setattr(InstagramAPI, "media", lambda self, shortcode: [{
        "pk": "123", "code": "ABC", "taken_at": 1700000000, "caption": {"text": "Weekend"},
        "user": {"pk": "456", "username": "alice", "full_name": "Alice"},
        "carousel_media": [item(1), item(2, video=True), item(3)],
    }])
    info = engine.probe("https://www.instagram.com/p/ABC/")
    assert info.photo_count == 2


def test_video_probe_falls_back_when_plain_http_inspection_is_denied(photo_engine):
    engine, adapter = photo_engine
    adapter.routes["https://example.com/watch"] = (b"Access denied", "text/html")
    original_send = adapter.send
    def denied(request, **kwargs):
        response = original_send(request, **kwargs)
        response.status_code = 403
        return response
    adapter.send = denied
    assert engine.probe("https://example.com/watch") is None


def test_photo_cancel_is_honored(photo_engine, tmp_path):
    engine, adapter = photo_engine
    url = "https://cdn.example/photo.png"
    adapter.routes[url] = (image_bytes(), "image/png")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloaderError) as error:
        download(engine, url, tmp_path, cancel=cancel)
    assert error.value.code == ErrorCode.CANCELLED


def test_html_cannot_be_saved_as_a_photo(photo_engine, tmp_path):
    engine, adapter = photo_engine
    url = "https://cdn.example/photo.jpg"
    adapter.routes[url] = (b"<html>login</html>", "image/jpeg")
    with pytest.raises(DownloaderError) as error:
        download(engine, url, tmp_path)
    assert error.value.code == ErrorCode.EXTRACTOR_FAILED


def test_heif_image_does_not_depend_on_pdf_converter_imports(photo_engine, tmp_path):
    import pillow_heif
    engine, adapter = photo_engine
    output = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (2, 2), "orange")).save(output)
    url = "https://cdn.example/photo.heic"
    adapter.routes[url] = (output.getvalue(), "image/heic")
    result = download(engine, url, tmp_path)
    assert result.path.suffix == ".heif"
    assert result.path.read_bytes() == output.getvalue()


@pytest.mark.parametrize("url", ["https://www.tiktok.com/@alice", "https://www.instagram.com/alice/", "https://www.pinterest.com/alice/board/"])
def test_profile_and_board_links_are_refused(photo_engine, url):
    engine, adapter = photo_engine
    with pytest.raises(DownloaderError) as error:
        engine.probe(url)
    assert error.value.code == ErrorCode.INVALID_URL
    assert adapter.seen == []


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com/p.png", "http://example.com:8000/p.png"])
def test_asset_urls_cannot_bypass_url_rules(photo_engine, url):
    engine, adapter = photo_engine
    with pytest.raises(DownloaderError):
        engine.probe(url)
    assert adapter.seen == []


async def test_photo_service_returns_image_mime_and_keeps_account_scope(service, fake_extractor):
    from dataclasses import replace
    from src.capabilities.media_downloader.utils.service import Caller
    fake_extractor.info = replace(fake_extractor.info, photo_count=1, duration=None, formats=[])
    fake_extractor.suffix = ".png"
    result = await service.probe("https://example.com/photo")
    assert result.photo_count == 1
    job = await service.start_download(Caller("alice"), result.url, "photos")
    event = await service.wait(job)
    assert event["type"] == "done"
    assert event["file"]["kind"] == "photo"
    assert event["file"]["mime"] == "image/png"
    assert service.list_files(Caller("bob")) == []
