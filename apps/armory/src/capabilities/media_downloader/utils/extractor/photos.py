"""Public single-post photos, with gallery-dl used only for URL discovery.
All HTTP stays in requests on the guarded thread; multi-photo posts become a numbered ZIP."""
from __future__ import annotations

import zipfile
from urllib.parse import unquote, urlsplit

import requests
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .models import DownloadedFile, DownloadProgress, MediaInfo
from .ytdlp import map_error
from ..errors import DownloaderError, ErrorCode
from ..policy.socket_guard import GUARD

MAX_PHOTOS = 100
MAX_METADATA_BYTES = 8 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
IMAGE_SUFFIXES = {"jpg", "jpeg", "png", "webp", "gif", "avif", "heic", "heif", "bmp", "tif", "tiff"}
FORMAT_SUFFIX = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif", "AVIF": ".avif",
                 "HEIF": ".heif", "BMP": ".bmp", "TIFF": ".tiff"}


def _check_url(url):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme in {"http", "https"} and parts.hostname and not parts.username
                 and not parts.password and parts.port in {None, 80, 443})
    except ValueError:
        valid = False
    if not valid:
        raise DownloaderError(ErrorCode.INVALID_URL, "Use a public HTTP(S) link on a standard web port, without credentials.")


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise DownloaderError(ErrorCode.CANCELLED, "The download was cancelled.")


def _read_bounded(response, limit, cancel=None):
    content = bytearray()
    try:
        for chunk in response.iter_content(CHUNK_SIZE):
            _cancelled(cancel)
            if len(content) + len(chunk) > limit:
                raise DownloaderError(ErrorCode.TOO_LARGE, "The photo or page exceeds the download size limit.")
            content.extend(chunk)
    finally:
        response.close()
    response._content = bytes(content)
    response._content_consumed = True


class PhotoSession(requests.Session):
    """HTTP(S) only; no ambient proxy/netrc, bounded metadata and redirect bodies."""
    def __init__(self):
        super().__init__()
        self.trust_env = False
        self.cancel = None
        self._requests = 0
        self.request_limit = 32
        self.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
        self.hooks["response"].append(self._redirect_body)

    def _redirect_body(self, response, **kwargs):
        if response.is_redirect:
            _read_bounded(response, CHUNK_SIZE, self.cancel)
        return response

    def send(self, request, **kwargs):
        _cancelled(self.cancel)
        self._requests += 1
        if self._requests > self.request_limit:
            raise DownloaderError(ErrorCode.EXTRACTOR_FAILED, "This photo post required too many requests. Try another link.")
        _check_url(request.url)
        stream = kwargs.get("stream", False)
        kwargs["stream"] = True
        kwargs["timeout"] = 20
        response = super().send(request, **kwargs)
        if not stream:
            _read_bounded(response, MAX_METADATA_BYTES, self.cancel)
        return response


def _social_host(host):
    return any(host == base or host.endswith("." + base) for base in ("tiktok.com", "instagram.com", "pinterest.com", "pin.it"))


class PhotoExtractor:
    """Inspect one public image or social post; preserve original photo bytes."""
    def __init__(self, *, guard=GUARD, session_factory=PhotoSession):
        register_heif_opener()
        self._guard = guard
        self._session_factory = session_factory
        guard.install()

    def _inspect(self, url, session):
        from gallery_dl import config, exception, extractor
        from gallery_dl.extractor.message import Message

        _check_url(url)
        parts = urlsplit(url)
        host = parts.hostname.lower()
        if host in {"vm.tiktok.com", "vt.tiktok.com", "pin.it"} or (host in {"tiktok.com", "www.tiktok.com"} and parts.path.startswith("/t/")):
            with session.get(url, stream=True) as response:
                response.raise_for_status()
                url = response.url
            parts = urlsplit(url)
            host = parts.hostname.lower()
        if not _social_host(host):
            with session.get(url, stream=True) as response:
                mime = response.headers.get("Content-Type", "").partition(";")[0].lower()
                if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif", "image/heic", "image/heif", "image/bmp", "image/tiff"}:
                    return None
                response.raise_for_status()
                title = unquote(parts.path.rsplit("/", 1)[-1]) or "Photo"
                if title.rpartition(".")[2].lower() in IMAGE_SUFFIXES:
                    title = title.rpartition(".")[0] or "Photo"
            return MediaInfo(title, None, None, None, url, photo_count=1), [url]

        # Do not load CLI/user config. Restrict discovery to a single post/pin;
        # never recurse into Message.Queue (profiles, boards, related posts).
        source = extractor.find(url)
        if source is not None and source.category == "instagram" and source.subcategory in {"reel", "reels", "tv"}:
            return None  # Preserve yt-dlp's existing Instagram video routes.
        if source is None or source.category not in {"tiktok", "instagram", "pinterest"} or source.subcategory not in {"post", "pin"}:
            raise DownloaderError(ErrorCode.INVALID_URL, "Paste a link to one photo post or pin, rather than a profile or board.")
        # gallery-dl's cache defaults outside this capability. Keep discovery's
        # anonymous tokens in memory; never load saved credentials or cookies.
        config.set(("cache",), "file", ":memory:")
        source.session = session
        options = {"photos": True, "videos": False, "audio": False, "covers": False,
                   "previews": False, "retries": 0, "timeout": 20, "sleep-request": 0,
                   "sleep-429": 0, "cookies": None, "username": None, "password": None}
        source.config = lambda key, default=None: options.get(key, default)
        photos = []
        title = "Photo post"
        uploader = None
        try:
            for message in source:
                _cancelled(session.cancel)
                if self._guard.blocked:
                    raise DownloaderError(ErrorCode.BLOCKED_HOST, "That address is not a public website.")
                if message[0] != Message.Url:
                    continue
                asset_url, metadata = message[1], message[2]
                extension = str(metadata.get("extension", "")).lower()
                if metadata.get("type") != "image" and extension not in IMAGE_SUFFIXES:
                    continue
                _check_url(asset_url)
                if asset_url in photos:
                    continue
                photos.append(asset_url)
                if len(photos) > MAX_PHOTOS:
                    raise DownloaderError(ErrorCode.TOO_LARGE, f"A post may contain at most {MAX_PHOTOS} photos.")
                title = str(metadata.get("title") or metadata.get("description") or metadata.get("caption") or title)
                uploader = str(metadata.get("user") or metadata.get("username") or "") or None
        except (exception.AuthenticationError, exception.AuthorizationError) as exc:
            raise DownloaderError(ErrorCode.LOGIN_REQUIRED, "This post requires a login and cannot be downloaded anonymously.") from exc
        _cancelled(session.cancel)
        if self._guard.blocked:
            raise DownloaderError(ErrorCode.BLOCKED_HOST, "That address is not a public website.")
        if source.status:
            raise DownloaderError(ErrorCode.EXTRACTOR_FAILED, "The photo post could not be read. It may require login or be unavailable.")
        if not photos:
            if "/photo/" in parts.path:
                raise DownloaderError(ErrorCode.EXTRACTOR_FAILED, "The photos could not be read. The post may be unavailable or require login.")
            return None  # video post: let yt-dlp handle it
        return MediaInfo(title, None, None, uploader, url, photo_count=len(photos)), photos

    def probe(self, url):
        with self._guard.active():
            try:
                with self._session_factory() as session:
                    result = self._inspect(url, session)
                    return result[0] if result else None
            except Exception as exc:
                raise map_error(exc, blocked=self._guard.blocked) from exc

    def download(self, url, preset, work_dir, *, max_bytes, max_duration_seconds, on_progress, cancel):
        with self._guard.active():
            try:
                with self._session_factory() as session:
                    session.cancel = cancel
                    _cancelled(cancel)
                    result = self._inspect(url, session)
                    if result is None:
                        raise DownloaderError(ErrorCode.INVALID_REQUEST, "This link no longer offers photos. Check it again.")
                    _, photos = result
                    # Discovery stays bounded separately from media requests.
                    # Allow every accepted photo and requests' bounded redirects.
                    session.request_limit += len(photos) * (session.max_redirects + 1)
                    paths = []
                    total_bytes = 0
                    for index, asset_url in enumerate(photos, 1):
                        _cancelled(cancel)
                        path = work_dir / f"{index:03}.image"
                        with session.get(asset_url, stream=True) as response, path.open("wb") as output:
                            response.raise_for_status()
                            for chunk in response.iter_content(CHUNK_SIZE):
                                _cancelled(cancel)
                                total_bytes += len(chunk)
                                if total_bytes > max_bytes:
                                    raise DownloaderError(ErrorCode.TOO_LARGE, "The photos exceed the download size limit.")
                                output.write(chunk)
                        try:
                            with Image.open(path) as image:
                                suffix = FORMAT_SUFFIX.get(image.format)
                                image.verify()
                            if suffix is None:
                                raise ValueError("unsupported image format")
                        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                            raise DownloaderError(ErrorCode.EXTRACTOR_FAILED, "The server did not return a supported photo.") from exc
                        target = path.with_suffix(suffix)
                        path.rename(target)
                        paths.append(target)
                        on_progress(DownloadProgress("downloading", round(index * 100 / len(photos), 1), None, None))
                    _cancelled(cancel)
                    if len(paths) == 1:
                        return DownloadedFile(paths[0])
                    on_progress(DownloadProgress("processing", 100, None, None))
                    archive_path = work_dir / "photos.zip"
                    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
                        for path in paths:
                            with path.open("rb") as source, archive.open(path.name, "w") as output:
                                while chunk := source.read(CHUNK_SIZE):
                                    _cancelled(cancel)
                                    output.write(chunk)
                    if archive_path.stat().st_size > max_bytes:
                        raise DownloaderError(ErrorCode.TOO_LARGE, "The photo archive exceeds the download size limit.")
                    return DownloadedFile(archive_path)
            except Exception as exc:
                raise map_error(exc, blocked=self._guard.blocked) from exc
