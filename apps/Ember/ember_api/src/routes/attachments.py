"""/api/attachments: text from a file attached to a chat question
(files.upload). The browser folds the text into the question it sends; the
originals for PDF/image attachments are stored in PDFMerger under the account;
other text attachments are read and discarded.

The file comes base64-encoded in JSON: every POST to ember_api is JSON
(see json_only.py), which keeps cross-site form posts out."""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.routes.server_info import get_server_info
from src.services.log_service import LogWriter
from src.services.mcp_server_info import McpServerInfo, McpServerRefused, McpServerUnavailable
from src.services.permissions import FILES_UPLOAD
from src.services.scribe import ScribeGateway
from src.services.capability_files import CapabilityFilesGateway
from src.services.text_extraction import MAX_FILE_BYTES, ExtractionError, extract_text_async

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

require_chat = require_permission(FILES_UPLOAD)


@router.get("/files/{file_id}/content")
async def attachment_content(
    request: Request,
    file_id: str = Path(pattern=r"^[A-Za-z0-9_-]{1,100}$"),
    account: Account = Depends(require_permission("files.download")),
):
    """Preview an owned chat attachment without a PDF workspace subscription."""
    client = CapabilityFilesGateway(request.app.state.upstream, request.app.state.settings.mcp_server_url,
                                    request.app.state.internal_token)
    return await client.stream("pdf", file_id, account, content=True, range_header=request.headers.get("range"))

# base64 is 4 characters per 3 bytes.
_MAX_BASE64 = (MAX_FILE_BYTES + 2) // 3 * 4


class AttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_MAX_BASE64)


class AttachmentTextOut(BaseModel):
    filename: str
    text: str
    char_count: int
    truncated: bool


@router.post("/text")
async def attachment_text(body: AttachmentIn, _account: Account = Depends(require_chat)) -> AttachmentTextOut:
    try:
        content = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data must be base64") from error
    # Only the last path part: a browser may send a full path.
    filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
    try:
        extracted = await extract_text_async(filename, content)
    except ExtractionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    return AttachmentTextOut(
        filename=extracted.filename,
        text=extracted.text,
        char_count=extracted.char_count,
        truncated=extracted.truncated,
    )


# The data tools read the whole file on mcp_server, which accepts only these.
_TABLE_SUFFIXES = (".csv", ".xlsx")


class AttachmentTableOut(BaseModel):
    table_id: str
    filename: str
    rows: int
    columns: list[str]
    sheet: str | None = None
    notes: list[str] = Field(default_factory=list)


@router.post("/table")
async def attachment_table(
    body: AttachmentIn,
    account: Account = Depends(require_chat),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> AttachmentTableOut:
    """Hands a .csv / .xlsx to mcp_server, which keeps the whole file as a table
    for the data tools and answers with its id. The text preview of the same
    file still comes from /text; this call is what lets the agent see all rows."""
    filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(_TABLE_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .csv and .xlsx files can be analysed.")
    try:
        content = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data must be base64") from error
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 15 MB")
    try:
        table = await info.upload_table(account, filename, content)
    except McpServerUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "mcp_server is unreachable") from error
    except McpServerRefused as error:
        if error.status in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            # Our own token was refused: a setup fault, not something the user did.
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "mcp_server is unreachable") from error
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    await logs.action(account, "attachments.table", f"Attached '{filename}' ({len(content):,} bytes) as a table")
    return AttachmentTableOut(
        table_id=table["table_id"],
        filename=str(table.get("filename", filename)),
        rows=int(table.get("rows", 0)),
        columns=[str(name) for name in table.get("columns", [])],
        sheet=table.get("sheet"),
        notes=[str(note) for note in table.get("notes", [])],
    )


class AttachmentPdfOut(AttachmentTextOut):
    file_id: str
    pages: int
    kind: str
    expires_at: float


@router.post("/pdf")
async def attachment_pdf(
    body: AttachmentIn,
    account: Account = Depends(require_chat),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> AttachmentPdfOut:
    """Keep originals for PDF tools; extracted text is an optional preview."""
    filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".heic")):
        raise HTTPException(400, "Upload a PDF or supported image")
    try:
        content = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(400, "data must be base64") from error
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "The file is larger than 15 MB")
    try:
        uploaded = await info.upload_pdf(account, filename, content)
    except McpServerUnavailable as error:
        raise HTTPException(502, "PDF upload is unavailable; check the pdf_merger extension") from error
    except McpServerRefused as error:
        raise HTTPException(502 if error.status in (401, 403) else 400, str(error)) from error
    text, chars, truncated = "", 0, False
    if filename.lower().endswith(".pdf"):
        try:
            extracted = await extract_text_async(filename, content)
            text, chars, truncated = extracted.text, extracted.char_count, extracted.truncated
        except ExtractionError:
            pass  # Scans and blank pages remain valid inputs for inspect/merge.
    await logs.action(account, "attachments.pdf", f"Attached '{filename}' ({len(content):,} bytes) for PDF tools")
    return AttachmentPdfOut(
        filename=filename,
        file_id=uploaded["file_id"],
        pages=uploaded["pages"],
        kind=uploaded["kind"],
        expires_at=uploaded["expires_at"],
        text=text,
        char_count=chars,
        truncated=truncated,
    )


_AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm")
# 20 MB, not Scribe's 25 MB: base64 of 25 MB would not fit ember_api's request cap for this path.
_MAX_AUDIO_BYTES = 20 * 1024 * 1024
_MAX_AUDIO_BASE64 = (_MAX_AUDIO_BYTES + 2) // 3 * 4


class AudioIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_MAX_AUDIO_BASE64)


class AttachmentAudioOut(BaseModel):
    filename: str
    file_id: str
    duration_s: float
    expires_at: float


@router.post("/audio")
async def attachment_audio(
    body: AudioIn,
    request: Request,
    account: Account = Depends(require_chat),
    logs: LogWriter = Depends(get_log_writer),
) -> AttachmentAudioOut:
    """Keep the original for Scribe's transcribe tool; the agent gets the file_id."""
    filename, content = _audio_content(body)
    gateway = ScribeGateway(request.app.state.upstream, request.app.state.settings.scribe_url,
                            request.app.state.internal_token)
    uploaded = await gateway.upload(account, filename, content)
    await logs.action(account, "attachments.audio", f"Attached '{filename}' ({len(content):,} bytes) for transcription")
    return AttachmentAudioOut(
        filename=filename, file_id=uploaded["file_id"], duration_s=float(uploaded["duration_s"]),
        expires_at=float(uploaded["expires_at"]),
    )


class DictationOut(BaseModel):
    text: str
    duration_s: float


def _audio_content(body: AudioIn) -> tuple[str, bytes]:
    """Keep dictation and attachments under identical audio validation rules."""
    filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not filename.lower().endswith(_AUDIO_SUFFIXES):
        raise HTTPException(400, "Upload an mp3, wav, m4a, ogg, flac or webm file")
    try:
        content = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(400, "data must be base64") from error
    if len(content) > _MAX_AUDIO_BYTES:
        raise HTTPException(413, "The audio is larger than 20 MB")
    return filename, content


@router.post("/dictate")
async def dictate(
    body: AudioIn,
    request: Request,
    account: Account = Depends(require_chat),
    logs: LogWriter = Depends(get_log_writer),
) -> DictationOut:
    """Return speech as draft text without asking the chat agent to transcribe it."""
    filename, content = _audio_content(body)
    gateway = ScribeGateway(request.app.state.upstream, request.app.state.settings.scribe_url,
                            request.app.state.internal_token)
    result = await gateway.transcribe(account, filename, content)
    await logs.action(account, "attachments.dictate", f"Transcribed {len(content):,} bytes of dictated audio")
    return DictationOut(text=result["text"], duration_s=float(result["duration_s"]))
