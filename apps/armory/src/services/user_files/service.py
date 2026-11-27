"""UserFiles: the one facade over stored files, shared by the file tools, the PDF tools and the HTTP routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.services.file_errors import ErrorCode, FileError
from src.services.link_signing import LinkSigner
from src.services.user_files.kinds import PAGED, UNSUPPORTED, classify
from src.services.user_files.names import safe_filename
from src.services.user_files.sniff import SNIFF_BYTES
from src.services.user_files.store import MB, FileStore, StoredFile

_NOT_AVAILABLE = "This file is not available. Upload it again."
HEARD_MIMES = frozenset({"audio/wav", "audio/mpeg"})  # the audio a model gateway accepts


@dataclass(frozen=True)
class Settings:
    """Store settings supplied by Armory; no environment or config loading here."""

    store_dir: Path
    public_base_url: str = "http://127.0.0.1:29600"
    file_ttl_seconds: int = 3600
    sweep_interval_seconds: int = 600
    download_link_seconds: int = 3600
    signing_key: bytes = b""
    max_file_bytes: int = 100 * MB
    max_session_bytes: int = 500 * MB
    max_upload_bytes: int = 15 * MB
    max_audio_upload_bytes: int = 20 * MB
    max_image_pixels: int = 80_000_000


async def chunks_of(content: bytes, size: int = 65536) -> AsyncIterator[bytes]:
    for start in range(0, len(content), size):
        yield content[start:start + size]


def _read_head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(SNIFF_BYTES)


class UserFiles:
    """Every operation takes the owner's account id; another account's file does not exist."""

    def __init__(self, store: FileStore, signer: LinkSigner, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self._signer = signer

    def _inspect(self, path: Path, kind: str) -> int:
        """Page count: refuse a damaged PDF or image; other kinds have no pages. Blocking."""
        if kind == "pdf":
            from src.services.user_files.pdfs import count_pages

            return count_pages(path)
        if kind == "image":
            from src.services.user_files.images import check_image

            check_image(path, self.settings.max_image_pixels)
            return 1
        return 0

    async def upload(
        self, owner: str, name: str | None, chunks: AsyncIterable[bytes], *,
        kinds: Collection[str] | None = None, unsupported: str = UNSUPPORTED,
    ) -> StoredFile:
        """Stream to disk, decide the kind, validate, then commit."""
        pending = await self.store.write_stream(owner, chunks)
        try:
            safe = safe_filename(name, "upload")
            # A caller that wants only PDF and images trusts nothing but the bytes.
            paged_only = kinds is not None and set(kinds) <= PAGED
            head = await asyncio.to_thread(_read_head, pending.path)
            kind, mime = classify("" if paged_only else safe, head, unsupported)
            if kinds is not None and kind not in kinds:
                raise FileError(ErrorCode.UNSUPPORTED_TYPE, unsupported)
            pages = await asyncio.to_thread(self._inspect, pending.path, kind)
        except BaseException:
            self.store.discard(pending)
            raise
        return await self.store.commit(pending, name=safe, mime=mime, kind=kind, pages=pages)

    def list(self, owner: str, kinds: Collection[str] | None = None) -> list[StoredFile]:
        return [file for file in self.store.list(owner) if kinds is None or file.kind in kinds]

    def get(self, file_id: str, owner: str, kinds: Collection[str] | None = None) -> StoredFile:
        file = self.store.get(file_id, owner)
        if kinds is not None and file.kind not in kinds:
            raise FileError(ErrorCode.FILE_NOT_FOUND, _NOT_AVAILABLE)
        return file

    def lookup(
        self, owner: str, file_ids: Sequence[str], kinds: Collection[str] | None = None,
    ) -> tuple[list[StoredFile], list[tuple[str, FileError]]]:
        """Look up each ID; one bad ID never aborts the rest."""
        files: list[StoredFile] = []
        failed: list[tuple[str, FileError]] = []
        for file_id in file_ids:
            try:
                files.append(self.get(file_id, owner, kinds))
            except FileError as error:
                failed.append((file_id, error))
        return files, failed

    def path(self, file: StoredFile) -> Path:
        return self.store.path(file)

    async def delete(self, file_id: str, owner: str, kinds: Collection[str] | None = None) -> None:
        self.get(file_id, owner, kinds)
        await self.store.delete(file_id, owner)

    def view(self, file: StoredFile, page: int | None = None) -> tuple[bytes, str]:
        """An image or one page of a PDF, small enough to show a model, or WAV or MP3 audio as stored: (bytes, media
        type). Blocking."""
        if file.kind == "pdf":
            if page is None or not 1 <= page <= file.pages:
                raise FileError(ErrorCode.INVALID_RANGE, f"Choose a page from 1 to {file.pages}.")
            from src.services.user_files.pdfs import view_page

            return view_page(self.path(file), page)
        if file.kind == "audio":
            if file.mime not in HEARD_MIMES:
                raise FileError(ErrorCode.UNSUPPORTED_TYPE, "Only WAV and MP3 audio can be heard.")
            if page is not None:
                raise FileError(ErrorCode.INVALID_REQUEST, "Audio has no pages.")
            return self.path(file).read_bytes(), file.mime
        if file.kind != "image":
            raise FileError(ErrorCode.UNSUPPORTED_TYPE, "That file is not an image, a PDF or audio.")
        if page is not None:
            raise FileError(ErrorCode.INVALID_REQUEST, "An image has no pages.")
        from src.services.user_files.images import view_image

        return view_image(self.path(file))

    def download_url(self, file: StoredFile, prefix: str = "/files") -> str:
        exp, sig = self._signer.sign(file.file_id)
        return f"{self.settings.public_base_url.rstrip('/')}{prefix}/{file.file_id}/download?exp={exp}&sig={sig}"

    def file_for_download(self, file_id: str, exp: int, sig: str) -> StoredFile:
        if not self._signer.verify(file_id, exp, sig):
            raise FileError(ErrorCode.FILE_NOT_FOUND, "This download link is invalid or has expired.")
        return self.store.get(file_id, None)

    async def sweep(self) -> int:
        return await self.store.sweep()


def build_user_files(settings: Settings) -> UserFiles:
    return UserFiles(
        FileStore(settings.store_dir, ttl_seconds=settings.file_ttl_seconds,
                  max_file_bytes=settings.max_file_bytes, max_session_bytes=settings.max_session_bytes),
        LinkSigner(settings.signing_key, settings.download_link_seconds),
        settings,
    )
