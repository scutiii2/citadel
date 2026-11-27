"""Account-owned files of every kind, independent of the calling protocol."""
from src.config import settings
from src.services import identity_context, untrusted
from src.services.user_files import runtime as files_runtime

from .contract import FailedFile, FileEntry, FilesResult


class FilesError(Exception):
    """A safe refusal for the caller."""


class FilesDesk:
    """The signed-in account's files; every method checks identity first."""

    def _owner(self) -> str:
        uid = identity_context.current_uid()
        if not uid:
            raise FilesError("Files need a signed-in user; this call carried no account identity.")
        return uid

    def _entry(self, files, file) -> FileEntry:
        return FileEntry(file_id=file.file_id, name=untrusted.fence(file.name, source="file name"), kind=file.kind,
                         pages=file.pages, size=file.size, expires_at=file.expires_at,
                         download_url=files.download_url(file))

    def _run(self, action):
        """`action(files)` on the files loop."""
        runtime = files_runtime.get_runtime(settings)

        async def perform():
            return action(runtime.files)

        return runtime.call(perform())

    def list_files(self) -> FilesResult:
        owner = self._owner()

        def action(files):
            found = files.list(owner)
            return FilesResult(files=[self._entry(files, f) for f in found], message=f"{len(found)} file(s).")
        return self._run(action)

    def inspect(self, file_ids: str) -> FilesResult:
        owner = self._owner()
        ids = [value.strip() for value in file_ids.split(",") if value.strip()]
        if len(ids) > 100:
            raise FilesError("Inspect at most 100 file IDs at a time.")

        def action(files):
            found, failed = files.lookup(owner, ids)
            return FilesResult(files=[self._entry(files, f) for f in found],
                               failed=[FailedFile(file_id=i, code=str(e.code), message=e.message) for i, e in failed],
                               message=f"Found {len(found)} of {len(ids)} file(s).")
        return self._run(action)

    def view(self, file_id: str) -> tuple[bytes, str]:
        """One owned image as (bytes, media type)."""
        owner = self._owner()
        files, file = self._run(lambda files: (files, files.get(file_id, owner)))
        # Decoding runs on this worker thread, not on the files loop.
        return files.view(file)


desk = FilesDesk()
