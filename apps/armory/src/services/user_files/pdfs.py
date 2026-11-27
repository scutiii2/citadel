"""Checks of a stored PDF. Blocking; pikepdf is imported only when a PDF is checked."""

from __future__ import annotations

from pathlib import Path

from src.services.file_errors import ErrorCode, FileError


def count_pages(path: Path) -> int:
    import pikepdf

    try:
        with pikepdf.open(path) as pdf:
            count = len(pdf.pages)
    except pikepdf.PasswordError as error:
        raise FileError(
            ErrorCode.ENCRYPTED_PDF, "This PDF is password-protected. Remove the password, then upload it again."
        ) from error
    except pikepdf.PdfError as error:
        raise FileError(ErrorCode.CORRUPT_FILE, "This PDF is damaged and can't be read.") from error
    if count == 0:
        raise FileError(ErrorCode.CORRUPT_FILE, "This PDF has no pages.")
    return count
