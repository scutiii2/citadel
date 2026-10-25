"""HTTP endpoint for chat_app to hand this server a file dropped into a command-form modal, so a tool path param can be filled.
A plain route, not a tool, so a model can't plant files; authenticated with the shared X-Internal-Token (constant-time), the first route here to check it inbound."""

from __future__ import annotations

import asyncio
import hmac

from uuid import uuid4

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.formparsers import MultiPartException
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from src.config import settings
from src.services import capability_registry
from src.capabilities.tables.utils import table_loader
from src.capabilities.tables.utils import tables
from src.services.identity_context import REQUESTER_UID_HEADER, REQUESTER_USERNAME_HEADER

# Deliberately tight, not a generic upload endpoint: no built-in tool consumes an uploaded file today.
# Extend only when a new file-shaped param needs another kind.
_ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


def _token_valid(request: Request) -> bool:
    """Mirrors chat_app/src/internal_routes.py's _token_valid(): an unset expected token must never validate against an empty header."""
    expected = settings.internal_api_token
    provided = request.headers.get("X-Internal-Token", "")
    if not expected:
        return False
    return hmac.compare_digest(expected, provided)


def _safe_extension(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    return ext if ext in _ALLOWED_EXTENSIONS else None


async def upload_file(request: Request) -> JSONResponse:
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)

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
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)

    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "filename"):
        return JSONResponse({"error": "'file' is required"}, status_code=400)

    filename = upload.filename or ""
    content = await upload.read()
    try:
        parsed = await asyncio.to_thread(table_loader.load_table, filename, content)
        table = tables.registry.add(
            request.headers.get(REQUESTER_USERNAME_HEADER, ""), filename, parsed, len(content)
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


async def upload_pdf(request: Request) -> JSONResponse:
    """Keep an original PDF/image in the native capability's account store."""
    if not _token_valid(request):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)
    if not request.headers.get(REQUESTER_UID_HEADER, "").strip():
        return JSONResponse({"error": "The requesting account is not identified"}, status_code=400)
    try:
        enabled = capability_registry.is_enabled("pdf")
    except KeyError:
        enabled = False
    if not enabled:
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)

    # Offline capabilities must not import their optional processing dependencies.
    try:
        from src.capabilities.pdf_merger import domain
        from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError
    except ImportError:
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)

    # Count the whole multipart stream before Starlette spools file parts.
    # Allow 64 KiB for the boundary and headers in addition to the file cap.
    received = 0
    original_receive = request.receive

    async def bounded_receive():
        nonlocal received
        message = await original_receive()
        received += len(message.get("body", b""))
        if received > 15 * 1024 * 1024 + 65536:
            # MultiPartException makes the parser close every spooled temp file.
            raise MultiPartException("The upload is larger than 15 MB")
        return message

    bounded_request = Request(request.scope, receive=bounded_receive)
    try:
        async with bounded_request.form(max_files=1, max_fields=0) as form:
            upload = form.get("file")
            if upload is None or not hasattr(upload, "filename"):
                return JSONResponse({"error": "'file' is required"}, status_code=400)
            filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
            content = await upload.read(15 * 1024 * 1024 + 1)
        if len(content) > 15 * 1024 * 1024:
            return JSONResponse({"error": "The file is larger than 15 MB"}, status_code=413)
        result = await asyncio.to_thread(domain.upload, filename, content)
        return JSONResponse(result.model_dump(mode="json"))
    except (HTTPException, MultiPartException):
        if received > 15 * 1024 * 1024 + 65536:
            return JSONResponse({"error": "The upload is larger than 15 MB"}, status_code=413)
        return JSONResponse({"error": "Invalid file upload"}, status_code=400)
    except domain.PdfError as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    except MergerError as error:
        if error.code == ErrorCode.INTERNAL:
            return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)
        return JSONResponse({"error": error.message}, status_code=400)
    except Exception:
        return JSONResponse({"error": "PDF capability is unavailable"}, status_code=503)


def install_upload_routes(app: Starlette) -> None:
    """Add the file-upload routes to an existing Starlette app."""
    app.add_route("/upload", upload_file, methods=["POST"])
    app.add_route("/upload/table", upload_table, methods=["POST"])
    app.add_route("/upload/pdf", upload_pdf, methods=["POST"])
