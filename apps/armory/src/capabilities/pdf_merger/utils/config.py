"""Internal immutable engine settings, built by the capability runtime."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MB = 1024 * 1024

@dataclass(frozen=True)
class Limits:
    """Hard caps that keep one caller from exhausting disk, memory or CPU."""

    max_file_bytes: int = 100 * MB
    max_session_bytes: int = 500 * MB
    max_segments: int = 50
    max_output_pages: int = 2000
    max_image_pixels: int = 80_000_000
    max_concurrent_merges: int = 2
    job_timeout_seconds: float = 120.0

    @classmethod
    def from_config(cls, raw: Mapping) -> Limits:
        default = cls()
        return cls(
            max_file_bytes=int(float(raw.get("max_file_mb", default.max_file_bytes / MB)) * MB),
            max_session_bytes=int(float(raw.get("max_session_mb", default.max_session_bytes / MB)) * MB),
            max_segments=int(raw.get("max_segments", default.max_segments)),
            max_output_pages=int(raw.get("max_output_pages", default.max_output_pages)),
            max_image_pixels=int(float(raw.get("max_image_megapixels", default.max_image_pixels / 1e6)) * 1_000_000),
            max_concurrent_merges=int(raw.get("max_concurrent_merges", default.max_concurrent_merges)),
            job_timeout_seconds=float(raw.get("job_timeout_seconds", default.job_timeout_seconds)),
        )


@dataclass(frozen=True)
class Settings:
    """Engine settings supplied by Armory; no standalone environment or config loading."""

    public_base_url: str = "http://127.0.0.1:8000"
    store_dir: Path = Path("specifics/pdf_merger/.data/store")
    log_dir: Path = Path("specifics/pdf_merger/.logs")
    file_ttl_seconds: int = 6 * 3600
    sweep_interval_seconds: int = 600
    download_link_seconds: int = 3600
    internal_api_token: str = ""
    signing_key: bytes = b""
    limits: Limits = field(default_factory=Limits)
    mcp_wait_seconds: float = 100.0
