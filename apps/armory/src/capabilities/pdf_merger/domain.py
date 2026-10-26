"""Account-owned PDF operations, independent of the calling protocol."""
from pathlib import Path

from src.config import settings
from src.services import identity_context, untrusted
from src.services.internal_token import is_exposed_without_token
from src.capabilities.pdf_merger.utils.pdf_runtime import get_runtime

from .contract import FailedItem, FileInfo, InspectResult, LinkedFileInfo, ListFilesResult, MergePlan, MergeToolResult
from .utils.service import Caller


class PdfError(Exception):
    """A safe refusal for the caller."""


class PdfDesk:
    """The signed-in account's PDF files; every method checks exposure and identity first."""

    def _check_exposure(self):
        if is_exposed_without_token(settings.host, settings.internal_api_token):
            raise PdfError("PDF files are disabled: configure INTERNAL_API_TOKEN or bind to loopback.")

    def _caller(self):
        self._check_exposure()
        uid = identity_context.current_uid()
        if not uid:
            raise PdfError("PDF files need a signed-in user; this call carried no account identity.")
        return Caller(uid)

    def _info(self, service, file):
        return LinkedFileInfo(**FileInfo.of(file).model_dump(exclude={"name"}),
                              name=untrusted.fence(file.name, source="PDF filename"),
                              download_url=service.download_url(file))

    def upload(self, name: str, content: bytes) -> FileInfo:
        caller = self._caller()
        runtime = get_runtime(settings)

        async def perform():
            async def chunks():
                for start in range(0, len(content), 65536):
                    yield content[start:start + 65536]
            return FileInfo.of(await runtime.service.upload(caller, name, chunks()))
        return runtime.call(perform())

    def inspect_files(self, file_ids: str) -> InspectResult:
        caller = self._caller()
        ids = [value.strip() for value in file_ids.split(",") if value.strip()]
        if len(ids) > 100:
            raise PdfError("Inspect at most 100 file IDs at a time.")
        runtime = get_runtime(settings)

        async def perform():
            files, failed = runtime.service.inspect(caller, ids)
            return InspectResult(files=[self._info(runtime.service, f) for f in files],
                                 failed=[FailedItem(file_id=i, code=str(e.code), message=e.message) for i, e in failed],
                                 message=f"Found {len(files)} of {len(ids)} file(s).")
        return runtime.call(perform())

    def list_files(self) -> ListFilesResult:
        caller = self._caller()
        runtime = get_runtime(settings)

        async def perform():
            files = runtime.service.list_files(caller)
            return ListFilesResult(files=[self._info(runtime.service, f) for f in files], message=f"{len(files)} file(s).")
        return runtime.call(perform())

    def merge(self, plan: MergePlan) -> MergeToolResult:
        caller = self._caller()
        runtime = get_runtime(settings)

        async def perform():
            result = await runtime.service.merge_and_wait(caller, plan)
            return MergeToolResult(**result.model_dump(exclude={"name"}),
                                   name=untrusted.fence(result.name, source="PDF filename"),
                                   message=f"Merged {result.pages} pages. Use the download link to save the PDF.")
        return runtime.call(perform())

    def download(self, file_id: str, exp: int, sig: str) -> tuple[Path, str]:
        self._check_exposure()
        runtime = get_runtime(settings)

        async def perform():
            file = runtime.service.file_for_download(file_id, exp, sig)
            return runtime.service.file_path(file), file.name
        return runtime.call(perform())


desk = PdfDesk()
