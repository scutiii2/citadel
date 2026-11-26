"""HTTP endpoint for chat_app to hand this server a file dropped into a command-form modal, so a tool path param can be filled.
A plain route, not a tool, so a model can't plant files; authenticated by signed service assertions."""

from __future__ import annotations

import asyncio
import logging

from uuid import uuid4

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.formparsers import MultiPartException
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from src.config import settings
from src.capabilities.tables.utils import table_loader
from src.capabilities.tables.utils import tables
from src.services.identity_context import current_uid, current_username
from src.citadel_auth import current_caller
from src.services.service_auth import install_auth
from src.services.file_errors import ErrorCode, FileError
from src.services.user_files import runtime as files_runtime
from src.services.user_files.kinds import PAGED, suffix_kind
from src.services.user_files.service import chunks_of

logger = logging.getLogger(__name__)

# Allowed on top of the file cap for the multipart boundary and headers.
_ENVELOPE = 65536
_PDF_ONLY = "This file type isn't supported. Upload a PDF or an image (JPG, PNG, WebP, TIFF, GIF or HEIC)."
_UNAVAILABLE = "File storage is unavailable"

# Deliberately tight, not a generic upload endpoint: no built-in tool consumes an uploaded file today.
# Extend only when a new file-shaped param needs another kind.
_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def _authenticated(request: Request) -> bool:
    """Only middleware-authenticated calls reach upload processing."""
    return current_caller() is not None


def _safe_extension(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    return ext if ext in _ALLOWED_EXTENSIONS else None


async def upload_file(request: Request) -> JSONResponse:
    if not _authenticated(request):
        return JSONResponse({"error": "Missing authenticated service caller"}, status_code=401)

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        return JSONResponse({"error": "'file' is required"}, status_code=400)

    ext = _safe_extension(upload.filename)
    if ext is None:
        allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
        return JSONResponse({"error": f"Unsupported file type - allowed: {allowed}"}, status_code=400)

    # A random name, never the client's filename, which is attacker-controlled and could escape uploads_dir or collide.
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    saved_path = settings.uploads_dir / f"{uuid4().hex}{ext}"
    saved_path.write_bytes(await upload.read())

    return JSONResponse({"path": str(saved_path.resolve())})


async def upload_table(request: Request) -> JSONResponse:
    """Keeps an uploaded CSV/XLSX as an in-memory table for the data tools; nothing is written to disk and the caller gets an opaque `table_id` bound to the requester.
    Parsing is blocking, so it runs in a worker thread."""
    if not _authenticated(request):
        return JSONResponse({"error": "Missing authenticated service caller"}, status_code=401)

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        return JSONResponse({"error": "'file' is required"}, status_code=400)

    filename = upload.filename or ""
    content = await upload.read()
    try:
        parsed = await asyncio.to_thread(table_loader.load_table, filename, content)
        table = tables.registry.add(
            current_username(), filename, parsed, len(content)
        )
    except tables.TableRefused as error:
        return JSONResponse({"error": str(error)}, status_code=400)

    return JSONResponse(
        {
            "table_id": table.id,
            "filename": table.filename,
            "rows": table.row_count,
            "columns": list(table.columns),
            "sheet": table.sheet,
            "notes": list(table.notes),
        }
    )


def _keep(owner: str, filename: str, content: bytes, kinds):
    runtime = files_runtime.get_runtime(settings)
    options = {"kinds": kinds, "unsupported": _PDF_ONLY} if kinds else {}
    return runtime.call(runtime.files.upload(owner, filename, chunks_of(content), **options))


def _too_large(limit: int) -> JSONResponse:
    return JSONResponse({"error": f"The file is larger than {limit // (1024 * 1024)} MB"}, status_code=413)


async def _store_upload(request: Request, kinds=None) -> JSONResponse:
    """Keep one uploaded file in the account's store."""
    if not _authenticated(request):
        return JSONResponse({"error": "Missing authenticated service caller"}, status_code=401)
    owner = current_uid()
    if not owner.strip():
        return JSONResponse({"error": "The requesting account is not identified"}, status_code=400)
    try:
        limits = (await asyncio.to_thread(files_runtime.get_runtime, settings)).files.settings
        largest = max(limits.max_upload_bytes, limits.max_audio_upload_bytes)
        # Count the whole multipart stream before Starlette spools file parts.
        received = 0
        original_receive = request.receive

        async def bounded_receive():
            nonlocal received
            message = await original_receive()
            received += len(message.get("body", b""))
            if received > largest + _ENVELOPE:
                # MultiPartException makes the parser close every spooled temp file.
                raise MultiPartException("The upload is too large")
            return message

        bounded_request = Request(request.scope, receive=bounded_receive)
        try:
            async with bounded_request.form(max_files=1, max_fields=0) as form:
                upload = form.get("file")
                if upload is None or not hasattr(upload, "filename"):
                    return JSONResponse({"error": "'file' is required"}, status_code=400)
                filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
                limit = (limits.max_audio_upload_bytes if not kinds and suffix_kind(filename) == "audio"
                         else limits.max_upload_bytes)
                content = await upload.read(limit + 1)
        except (HTTPException, MultiPartException):
            if received > largest + _ENVELOPE:
                return _too_large(largest)
            return JSONResponse({"error": "Invalid file upload"}, status_code=400)
        if len(content) > limit:
            return _too_large(limit)
        stored = await asyncio.to_thread(_keep, owner, filename, content, kinds)
        return JSONResponse({"file_id": stored.file_id, "name": stored.name, "kind": stored.kind,
                             "pages": stored.pages, "size": stored.size, "expires_at": stored.expires_at})
    except FileError as error:
        if error.code == ErrorCode.INTERNAL:
            return JSONResponse({"error": _UNAVAILABLE}, status_code=503)
        return JSONResponse({"error": error.message}, status_code=400)
    except Exception:
        logger.exception("Upload failed")
        return JSONResponse({"error": _UNAVAILABLE}, status_code=503)


async def upload_any(request: Request) -> JSONResponse:
    return await _store_upload(request)


async def upload_pdf(request: Request) -> JSONResponse:
    """The older name Stronghold uses for PDF and image uploads."""
    return await _store_upload(request, PAGED)


def install_upload_routes(app: Starlette) -> None:
    """Add the file-upload routes to an existing Starlette app."""
    install_auth(app)
    app.add_route("/upload", upload_file, methods=["POST"])
    app.add_route("/upload/table", upload_table, methods=["POST"])
    app.add_route("/upload/pdf", upload_pdf, methods=["POST"])
    app.add_route("/upload/file", upload_any, methods=["POST"])
