"""Which uploads Armory keeps, and what kind each one is."""

from __future__ import annotations

from pathlib import PurePosixPath

from src.services.file_errors import ErrorCode, FileError
from src.services.user_files.sniff import sniff_mime

PAGED = frozenset({"pdf", "image"})
UNSUPPORTED = "This file type isn't supported."

# The same suffixes Stronghold can make a text preview of.
_TEXT = (".txt .md .markdown .tsv .json .log .ini .cfg .conf .yaml .yml .xml .html .htm .css .sql .py .js .ts .tsx "
         ".jsx .vue .java .c .h .cpp .hpp .cs .go .rb .php .sh .bat .ps1 .rs .kt .swift .toml").split()
_OFFICE = "application/vnd.openxmlformats-officedocument."
_BY_SUFFIX: dict[str, tuple[str, str]] = {
    **{suffix: ("text", "text/plain") for suffix in _TEXT},
    ".docx": ("document", _OFFICE + "wordprocessingml.document"),
    ".csv": ("table", "text/csv"),
    ".xlsx": ("table", _OFFICE + "spreadsheetml.sheet"),
    ".xlsm": ("table", "application/vnd.ms-excel.sheet.macroEnabled.12"),
    ".mp3": ("audio", "audio/mpeg"), ".wav": ("audio", "audio/wav"), ".m4a": ("audio", "audio/mp4"),
    ".ogg": ("audio", "audio/ogg"), ".flac": ("audio", "audio/flac"), ".webm": ("audio", "audio/webm"),
}


def suffix_kind(name: str) -> str | None:
    """The kind a name's suffix stands for; None for PDF, images and anything unknown."""
    known = _BY_SUFFIX.get(PurePosixPath(name.lower()).suffix)
    return known[0] if known else None


def classify(name: str, head: bytes, unsupported: str = UNSUPPORTED) -> tuple[str, str]:
    """(kind, media type). PDF and image are told by their bytes; the other kinds by suffix."""
    known = _BY_SUFFIX.get(PurePosixPath(name.lower()).suffix)
    if known:
        return known
    mime = sniff_mime(head)
    if mime:
        return ("pdf" if mime == "application/pdf" else "image"), mime
    raise FileError(ErrorCode.UNSUPPORTED_TYPE, unsupported)
