"""MCP tool result models. Each ends with a human-readable ``message``."""

from __future__ import annotations

from pydantic import BaseModel

from src.capabilities.media_downloader.utils.models import FileInfo, JobStatus, ProbeResult, PackageInfo


class ProbeToolResult(ProbeResult):
    message: str


class DownloadStarted(BaseModel):
    job_id: str
    message: str


class StatusToolResult(JobStatus):
    message: str


class ListFilesResult(BaseModel):
    files: list[FileInfo]
    message: str


class PackageFailure(BaseModel):
    url: str
    code: str
    message: str


class PackageToolResult(BaseModel):
    package: PackageInfo
    failed: list[PackageFailure] = []
    message: str


class ListPackagesResult(BaseModel):
    packages: list[PackageInfo]
    message: str
