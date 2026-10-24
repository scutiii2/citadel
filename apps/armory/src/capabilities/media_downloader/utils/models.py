"""Request and response models shared by the REST routers and MCP tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PresetOption(BaseModel):
    id: str
    label: str
    kind: str
    estimated_bytes: int | None = None
    blocked: bool = False
    code: str | None = None  # error code when blocked
    reason: str | None = None  # plain-language reason when blocked


class ProbeResult(BaseModel):
    url: str
    title: str
    duration: float | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    options: list[PresetOption]
    photo_count: int = 0


from src.capabilities.media_downloader.utils.store.file_store import StoredFile  # noqa: E402  (kept at the bottom to keep the top of the file model-only)


class FileInfo(BaseModel):
    file_id: str
    name: str
    kind: str  # video, audio, photo (image/ZIP), or package (ZIP)
    mime: str
    size: int
    duration: float | None = None
    expires_at: float
    download_url: str

    @classmethod
    def of(cls, stored: StoredFile, download_url: str) -> FileInfo:
        return cls(
            file_id=stored.file_id,
            name=stored.name,
            kind=stored.kind,
            mime=stored.mime,
            size=stored.size,
            duration=stored.duration,
            expires_at=stored.expires_at,
            download_url=download_url,
        )


class ErrorInfo(BaseModel):
    code: str
    message: str


class JobStatus(BaseModel):
    job_id: str
    state: str  # queued | downloading | processing | done | error
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    file: FileInfo | None = None
    error: ErrorInfo | None = None


class ProbeRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    preset: str


class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class PackageAdd(DownloadRequest):
    url: str = Field(min_length=1, max_length=8192)


class PackageItem(BaseModel):
    item_id: str
    url: str
    preset: str
    title: str | None = None
    state: str = 'pending'
    error: ErrorInfo | None = None


class PackageInfo(BaseModel):
    package_id: str
    name: str
    state: str = 'draft'
    items: list[PackageItem] = Field(default_factory=list)
    job_id: str | None = None
    status: JobStatus | None = None
