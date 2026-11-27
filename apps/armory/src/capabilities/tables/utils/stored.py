"""An uploaded CSV or Excel file in the account's file store, read as a table."""

from __future__ import annotations

from src.capabilities.tables.utils import table_loader
from src.capabilities.tables.utils.tables import MAX_FILE_BYTES, ParsedTable
from src.config import settings
from src.services import identity_context
from src.services.file_errors import FileError
from src.services.user_files import runtime as files_runtime


def load_stored(file_id: str) -> tuple[str, ParsedTable, int] | None:
    """The signed-in account's stored table file `file_id` as (file name, parsed table, size in bytes).
    None when the id is not a file of theirs, the file is gone, or it is no table. Blocking; may raise `TableRefused`."""
    owner = identity_context.current_uid()
    if not owner or not file_id.startswith("f_"):
        return None
    runtime = files_runtime.get_runtime(settings)

    async def find():
        file = runtime.files.get(file_id, owner, kinds={"table"})
        return file, runtime.files.path(file)

    try:
        file, path = runtime.call(find())
        if file.size > MAX_FILE_BYTES:
            return None
        content = path.read_bytes()
    except (FileError, OSError):
        return None
    return file.name, table_loader.load_table(file.name, content), file.size
