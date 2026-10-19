"""PDF request and result schemas."""
from pydantic import BaseModel

from .utils.models import FileInfo, MergePlan, MergeResult, OutputOptions, Segment


class FailedItem(BaseModel):
    file_id: str
    code: str
    message: str


class LinkedFileInfo(FileInfo):
    download_url: str


class InspectResult(BaseModel):
    files: list[LinkedFileInfo]
    failed: list[FailedItem]
    message: str


class ListFilesResult(BaseModel):
    files: list[LinkedFileInfo]
    message: str


class MergeToolResult(MergeResult):
    message: str
