"""Result schemas of the file tools."""
from pydantic import BaseModel


class FileEntry(BaseModel):
    file_id: str
    name: str
    kind: str
    pages: int
    size: int
    expires_at: float
    kept: bool = False  # held by a chat, so it does not expire while that chat exists
    download_url: str


class FailedFile(BaseModel):
    file_id: str
    code: str
    message: str


class FilesResult(BaseModel):
    files: list[FileEntry]
    failed: list[FailedFile] = []
    message: str
