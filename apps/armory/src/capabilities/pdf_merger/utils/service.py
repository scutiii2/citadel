"""MergeService: the one facade the REST routers and MCP tools call.
Routers and tools hold no logic of their own."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.capabilities.pdf_merger.utils.config import Limits, Settings
from src.capabilities.pdf_merger.utils.converters.base import ImageOptions
from src.capabilities.pdf_merger.utils.converters.registry import ConverterRegistry, default_registry
from src.capabilities.pdf_merger.utils.engine.assembler import AssemblyPart, Assembler
from src.capabilities.pdf_merger.utils.engine.planner import ExpandedPlan, expand_plan
from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError
from src.capabilities.pdf_merger.utils.jobs.job_queue import Job, JobQueue, ProgressFn
from src.capabilities.pdf_merger.utils.models import MergePlan, MergeResult, OutputOptions
from src.services.user_files.store import FileStore, StoredFile
from src.services.user_files.names import ensure_pdf_suffix, file_stem, safe_filename
from src.services.user_files.kinds import PAGED
from src.services.user_files.service import Settings as FilesSettings, UserFiles, build_user_files


@dataclass(frozen=True)
class Caller:
    """Owner scope. Authentication never grants access to another owner's files."""

    session: str
    privileged: bool = False

    @property
    def scope(self) -> str:
        return self.session


def _raise_if_cancelled(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise MergerError(ErrorCode.MERGE_TIMEOUT, "The merge took too long and was stopped. Try fewer pages.")


_PAGED_UNSUPPORTED = "This file type isn't supported. Upload a PDF or an image (JPG, PNG, WebP, TIFF, GIF or HEIC)."


class MergeService:
    """PDF's view of the shared files (PDF and images only), plus merging."""

    def __init__(
        self,
        *,
        files: UserFiles,
        registry: ConverterRegistry,
        assembler: Assembler,
        jobs: JobQueue,
        limits: Limits,
        file_ttl_seconds: int,
        mcp_wait_seconds: float = 100.0,
    ) -> None:
        self._files = files
        self._store = files.store
        self._registry = registry
        self._assembler = assembler
        self._jobs = jobs
        self._limits = limits
        self._file_ttl = file_ttl_seconds
        self._mcp_wait_seconds = mcp_wait_seconds

    @property
    def store(self) -> FileStore:
        return self._store

    # --- files -------------------------------------------------------------

    async def upload(self, caller: Caller, name: str | None, chunks: AsyncIterable[bytes]) -> StoredFile:
        return await self._files.upload(caller.session, name, chunks, kinds=PAGED, unsupported=_PAGED_UNSUPPORTED)

    def list_files(self, caller: Caller) -> list[StoredFile]:
        return self._files.list(caller.session, PAGED)

    def get_file(self, caller: Caller, file_id: str) -> StoredFile:
        return self._files.get(file_id, caller.scope, PAGED)

    def file_path(self, file: StoredFile) -> Path:
        return self._files.path(file)

    async def delete_file(self, caller: Caller, file_id: str) -> None:
        # Deletes use the same owner scope as reads and merges.
        await self._files.delete(file_id, caller.session, PAGED)

    def inspect(self, caller: Caller, file_ids: Sequence[str]) -> tuple[list[StoredFile], list[tuple[str, MergerError]]]:
        return self._files.lookup(caller.scope, file_ids, PAGED)

    # --- links -------------------------------------------------------------

    def download_url(self, file: StoredFile) -> str:
        return self._files.download_url(file, "/pdf/files")

    def file_for_download(self, file_id: str, exp: int, sig: str) -> StoredFile:
        return self._files.file_for_download(file_id, exp, sig)

    # --- merging -----------------------------------------------------------

    def start_merge(self, caller: Caller, plan: MergePlan) -> Job:
        """Validate now (errors raise immediately), then queue the work."""
        expanded = expand_plan(plan, lambda file_id: self.get_file(caller, file_id), self._limits)
        return self._jobs.submit(
            caller.session,
            expanded.total_pages,
            lambda progress, cancel: self._run_merge(caller.session, expanded, plan.output, progress, cancel),
        )

    async def merge_and_wait(self, caller: Caller, plan: MergePlan) -> MergeResult:
        job = self.start_merge(caller, plan)
        try:
            # wait_for cancels (and awaits) the inner wait on expiry, so nothing dangles
            final = await asyncio.wait_for(self._jobs.wait(job), self._mcp_wait_seconds)
        except asyncio.TimeoutError:
            self._jobs.cancel(job)
            raise MergerError(
                ErrorCode.MERGE_TIMEOUT,
                f"The merge took longer than {self._mcp_wait_seconds:g} seconds and was stopped. Try fewer pages.",
            ) from None
        if final.get("type") != "done":
            raise MergerError(ErrorCode(final.get("code", "internal_error")), final.get("message", "The merge failed."))
        return MergeResult.model_validate({k: v for k, v in final.items() if k != "type"})

    def get_job(self, caller: Caller, job_id: str) -> Job:
        return self._jobs.get(job_id, caller.scope)

    async def _run_merge(
        self, session: str, expanded: ExpandedPlan, output: OutputOptions, progress: ProgressFn, cancel: threading.Event
    ) -> dict:
        work_dir = await self._store.make_work_dir()
        try:
            parts: list[AssemblyPart] = []
            for segment in expanded.segments:
                _raise_if_cancelled(cancel)
                converter = self._registry.for_mime(segment.file.mime)
                pdf_path = await converter.to_pdf(
                    self._store.path(segment.file), work_dir, segment.image_options or ImageOptions()
                )
                parts.append(
                    AssemblyPart(
                        pdf_path=pdf_path,
                        pages=segment.pages,
                        rotate=segment.rotate,
                        bookmark=file_stem(segment.file.name),
                        group_key=segment.file.file_id,
                    )
                )
            pending = self._store.new_pending(session)
            try:
                pages = await self._assembler.assemble(
                    parts, pending.path, title=output.title, author=output.author, bookmarks=output.bookmarks, on_page=progress, cancel=cancel
                )
                stored = await self._store.commit(
                    pending,
                    name=ensure_pdf_suffix(safe_filename(output.filename, "merged.pdf")),
                    mime="application/pdf",
                    kind="pdf",
                    pages=pages,
                )
            except BaseException:
                self._store.discard(pending)
                raise
        finally:
            await self._store.remove_work_dir(work_dir)
        return MergeResult(
            file_id=stored.file_id,
            name=stored.name,
            pages=stored.pages,
            size=stored.size,
            expires_at=stored.expires_at,
            download_url=self.download_url(stored),
        ).model_dump()

    # --- housekeeping ------------------------------------------------------

    async def sweep(self) -> int:
        """Delete expired files and forget old jobs."""
        removed = await self._store.sweep()
        self._jobs.prune(older_than=time.time() - self._file_ttl)
        return removed


def build_service(settings: Settings, files: UserFiles | None = None) -> MergeService:
    """Wire a MergeService. Without `files` it makes a private store from `settings` (tests)."""
    limits = settings.limits
    files = files or build_user_files(FilesSettings(
        store_dir=settings.store_dir, public_base_url=settings.public_base_url,
        file_ttl_seconds=settings.file_ttl_seconds, download_link_seconds=settings.download_link_seconds,
        signing_key=settings.signing_key, max_file_bytes=limits.max_file_bytes,
        max_session_bytes=limits.max_session_bytes, max_image_pixels=limits.max_image_pixels,
    ))
    return MergeService(
        files=files,
        registry=default_registry(files.settings.max_image_pixels),
        assembler=Assembler(),
        jobs=JobQueue(limits.max_concurrent_merges, limits.job_timeout_seconds),
        limits=limits,
        file_ttl_seconds=files.settings.file_ttl_seconds,
        mcp_wait_seconds=settings.mcp_wait_seconds,
    )
