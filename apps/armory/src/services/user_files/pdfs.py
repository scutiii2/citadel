"""Checks and page pictures of a stored PDF. Blocking; the PDF libraries are imported only when used."""

from __future__ import annotations

import io
import threading
from pathlib import Path

from src.services.file_errors import ErrorCode, FileError

# PDFium is not thread-safe: one page is drawn at a time.
_DRAWING = threading.Lock()


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


def view_page(path: Path, page: int) -> tuple[bytes, str]:
    """One page (counted from 1) as (JPEG bytes, media type), small enough to show a model. Blocking."""
    import pypdfium2

    from src.services.user_files.images import VIEW_MAX_EDGE

    try:
        with _DRAWING:
            document = pypdfium2.PdfDocument(path)
            try:
                sheet = document[page - 1]
                bitmap = sheet.render(scale=VIEW_MAX_EDGE / max(sheet.get_size()))
                # convert() copies the pixels out of PDFium's buffer before the document closes.
                picture = bitmap.to_pil().convert("RGB")
            finally:
                document.close()
    except pypdfium2.PdfiumError as error:
        raise FileError(ErrorCode.CORRUPT_FILE, "This PDF page can't be drawn.") from error
    picture.thumbnail((VIEW_MAX_EDGE, VIEW_MAX_EDGE))
    buffer = io.BytesIO()
    picture.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue(), "image/jpeg"
