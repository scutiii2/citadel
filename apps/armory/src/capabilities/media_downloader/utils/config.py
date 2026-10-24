"""Ported service settings and caps; armory supplies paths and deployment values."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
MB = 1024 * 1024

@dataclass(frozen=True)
class Limits:
    """Hard caps that keep one caller from exhausting disk, bandwidth or CPU."""

    max_file_bytes: int = 500 * MB
    max_duration_seconds: float = 2 * 3600
    max_session_bytes: int = 2048 * MB
    max_concurrent_downloads: int = 2
    max_queued_downloads: int = 8
    job_timeout_seconds: float = 30 * 60

    @classmethod
    def from_config(cls, raw: Mapping) -> Limits:
        default = cls()
        return cls(
            max_file_bytes=int(float(raw.get("max_file_mb", default.max_file_bytes / MB)) * MB),
            max_duration_seconds=float(raw.get("max_duration_minutes", default.max_duration_seconds / 60)) * 60,
            max_session_bytes=int(float(raw.get("max_session_mb", default.max_session_bytes / MB)) * MB),
            max_concurrent_downloads=int(raw.get("max_concurrent_downloads", default.max_concurrent_downloads)),
            max_queued_downloads=int(raw.get("max_queued_downloads", default.max_queued_downloads)),
            job_timeout_seconds=float(raw.get("job_timeout_minutes", default.job_timeout_seconds / 60)) * 60,
        )


@dataclass(frozen=True)
class Settings:
    """Everything the service needs at startup. Built once by load_settings()."""

    host: str = "127.0.0.1"
    port: int = 8050
    public_base_url: str = "http://127.0.0.1:8050"
    web_origin: str = "http://127.0.0.1:5175"
    store_dir: Path = Path("specifics/media_downloader/.data/store")
    log_dir: Path = Path("specifics/media_downloader/.logs")
    file_ttl_seconds: int = 6 * 3600
    sweep_interval_seconds: int = 600
    download_link_seconds: int = 3600
    internal_api_token: str = ""
    signing_key: bytes = b""
    limits: Limits = field(default_factory=Limits)
