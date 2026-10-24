"""Dispatch photo posts and images alongside yt-dlp video/music downloads."""
from urllib.parse import urlsplit

from src.utils.catalog import catalog
from .photos import IMAGE_SUFFIXES, PhotoExtractor
from .ytdlp import YtDlpExtractor
from ..errors import DownloaderError, ErrorCode


@catalog
class MediaExtractor:
    def __init__(self):
        self._photos = PhotoExtractor()
        self._video = YtDlpExtractor()

    def probe(self, url):
        try:
            photo = self._photos.probe(url)
        except DownloaderError as error:
            # A browser-like yt-dlp handler may fetch a video page that plain
            # HTTP cannot. Never retry a policy refusal through another engine.
            path = urlsplit(url).path.lower()
            explicit_photo = "/photo/" in path or path.rpartition(".")[2] in IMAGE_SUFFIXES
            if error.code not in {ErrorCode.EXTRACTOR_FAILED, ErrorCode.LOGIN_REQUIRED} or explicit_photo:
                raise
            photo = None
        return photo or self._video.probe(url)

    def download(self, url, preset, work_dir, **kwargs):
        engine = self._photos if preset.kind == "photo" else self._video
        return engine.download(url, preset, work_dir, **kwargs)
