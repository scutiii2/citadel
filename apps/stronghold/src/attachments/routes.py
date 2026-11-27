"""/attachments: files attached to a chat question, and dictation (files.upload at Portcullis).

The file comes base64-encoded in JSON. Text is read here and sent back; the files themselves go to
Armory. Stronghold sends audio and documents to the configured Scribe and Reader origins.
Portcullis checks the login and permissions and relays browser streams.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from pathlib import PurePosixPath
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.attachments.extraction import MAX_FILE_BYTES, PLAIN_TEXT_SUFFIXES, ExtractionError, extract_text_async
from src.attachments.reading import read_with_reader, transcribe_with_scribe
from src.attachments.services import ArmoryUploads
from src.platform import PortcullisClient
from src.requester import Requester, current_requester
from src.tool_services.client import ToolServices

router = APIRouter(prefix="/attachments", tags=["attachments"])

# base64 is 4 characters per 3 bytes.
_MAX_BASE64 = (MAX_FILE_BYTES + 2) // 3 * 4
_TABLE_SUFFIXES = (".csv", ".xlsx")
_PDF_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".heic")
_AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm")
_DOCUMENT_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp")
# 20 MB, not Scribe's 25 MB: base64 of 25 MB would not fit the request cap for this path.
_MAX_AUDIO_BYTES = 20 * 1024 * 1024
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
# Files whose text Stronghold can read as a preview.
_PREVIEW_SUFFIXES = PLAIN_TEXT_SUFFIXES | {".pdf", ".docx", ".xlsx", ".xlsm"}
_READ_NOTES = {None: "", "reader": "; read by Reader", "pages": "; its pages are shown to the model",
               "scribe": "; transcribed by Scribe", "listen": "; to be transcribed by Legion"}


def _base64(size: int) -> int:
    return (size + 2) // 3 * 4


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


def get_uploads(request: Request) -> ArmoryUploads:
    return request.app.state.uploads


def get_connections(request: Request) -> ToolServices:
    return request.app.state.connections


class FileIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_MAX_BASE64)


class AudioIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_base64(_MAX_AUDIO_BYTES))


class DocumentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_base64(_MAX_DOCUMENT_BYTES))


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_base64(_MAX_AUDIO_BYTES))


class TextOut(BaseModel):
    filename: str
    text: str
    char_count: int
    truncated: bool


class TableOut(BaseModel):
    table_id: str
    filename: str
    rows: int
    columns: list[str]
    sheet: str | None = None
    notes: list[str] = Field(default_factory=list)


class PdfOut(TextOut):
    file_id: str
    pages: int
    kind: str
    expires_at: float


class AudioOut(BaseModel):
    filename: str
    file_id: str
    duration_s: float
    expires_at: float


class DocumentOut(TextOut):
    """What Reader read; `pages` (with no text) means the caller should show the model the pages instead."""

    read: Literal["reader", "pages"]


class FileOut(TextOut):
    """One uploaded file. `file_id` is None when Armory could not keep it and only its text is attached."""

    file_id: str | None = None
    kind: str = "text"
    size: int
    pages: int | None = None
    expires_at: float | None = None
    table: TableOut | None = None
    # set only for a PDF with no text of its own, and for audio
    read: Literal["reader", "pages", "scribe", "listen"] | None = None


class DictationOut(BaseModel):
    text: str
    duration_s: float


def _name(filename: str) -> str:
    """Only the last path part: a browser may send a full path."""
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _decode(data: str, limit: int = MAX_FILE_BYTES, too_big: str = "The file is larger than 15 MB") -> bytes:
    try:
        content = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data must be base64") from error
    if len(content) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, too_big)
    return content


def _table_out(table: dict, filename: str) -> TableOut:
    return TableOut(table_id=table["table_id"], filename=str(table.get("filename", filename)),
                    rows=int(table.get("rows", 0)), columns=[str(name) for name in table.get("columns", [])],
                    sheet=table.get("sheet"), notes=[str(note) for note in table.get("notes", [])])


def _audio(body: AudioIn) -> tuple[str, bytes]:
    """Dictation and attached audio follow the same rules."""
    filename = _name(body.filename)
    if not filename.lower().endswith(_AUDIO_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload an mp3, wav, m4a, ogg, flac or webm file")
    return filename, _decode(body.data, _MAX_AUDIO_BYTES, "The audio is larger than 20 MB")


@router.post("/text")
async def attachment_text(body: FileIn, _who: Requester = Depends(current_requester)) -> TextOut:
    try:
        content = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data must be base64") from error
    try:
        extracted = await extract_text_async(_name(body.filename), content)
    except ExtractionError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    return TextOut(filename=extracted.filename, text=extracted.text, char_count=extracted.char_count,
                   truncated=extracted.truncated)


@router.post("/file")
async def attachment_file(body: UploadIn, who: Requester = Depends(current_requester),
                          uploads: ArmoryUploads = Depends(get_uploads),
                          connections: ToolServices = Depends(get_connections),
                          platform: PortcullisClient = Depends(get_platform)) -> FileOut:
    """One route for every file: Armory keeps the original, and its text is read here as a preview."""
    filename = _name(body.filename)
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in _PREVIEW_SUFFIXES and suffix not in _PDF_SUFFIXES and suffix not in _AUDIO_SUFFIXES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Can't read '{suffix or 'extensionless'}' files - try a text, code, image, audio, .pdf, .docx or .xlsx file.")
    content = _decode(body.data, _MAX_AUDIO_BYTES, "The file is larger than 20 MB")
    preview = None
    if suffix in _PREVIEW_SUFFIXES:
        try:
            preview = await extract_text_async(filename, content)
        except ExtractionError as error:
            if suffix != ".pdf":  # a scan has no text and is still worth keeping
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    async def table() -> dict | None:
        """The data tools' copy of a spreadsheet; the file stays attached without it."""
        if suffix not in _TABLE_SUFFIXES:
            return None
        try:
            return await uploads.table(who, filename, content)
        except HTTPException:
            return None

    stored, registered = await asyncio.gather(uploads.file(who, filename, content), table(), return_exceptions=True)
    if isinstance(registered, BaseException):
        raise registered
    if isinstance(stored, BaseException):
        # With readable text the question can still go out: always during an outage, and for text-like files, which
        # never needed the store, after a refusal too.
        outage = isinstance(stored, HTTPException) and stored.status_code == status.HTTP_502_BAD_GATEWAY
        if not isinstance(stored, HTTPException) or preview is None or not (outage or suffix not in _PDF_SUFFIXES):
            raise stored
        stored = None
    read, found = None, None
    if stored is not None:
        if suffix == ".pdf" and preview is None:  # a scan: no text of its own
            found = await read_with_reader(connections, suffix, content)
            read = "pages" if found is None else "reader"
        elif suffix in _AUDIO_SUFFIXES:
            found = await transcribe_with_scribe(connections, suffix, content)
            read = "listen" if found is None else "scribe"
        note = _READ_NOTES[read]
        await platform.log_action(who.uid, "attachments.file", f"Attached '{filename}' ({len(content):,} bytes){note}")
    text, truncated = found or ((preview.text, preview.truncated) if preview else ("", False))
    kept = {} if stored is None else {"file_id": stored["file_id"], "kind": stored["kind"],
                                      "pages": stored["pages"] or None, "expires_at": stored["expires_at"]}
    return FileOut(filename=filename, size=len(content), text=text, char_count=len(text), truncated=truncated,
                   table=_table_out(registered, filename) if registered else None, read=read, **kept)


@router.post("/table")
async def attachment_table(body: FileIn, who: Requester = Depends(current_requester),
                           uploads: ArmoryUploads = Depends(get_uploads),
                           platform: PortcullisClient = Depends(get_platform)) -> TableOut:
    """Armory keeps the whole file as a table for the data tools. The text preview of the same file
    still comes from /text; this call is what lets the agent see all rows."""
    filename = _name(body.filename)
    if not filename.lower().endswith(_TABLE_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .csv and .xlsx files can be analysed.")
    content = _decode(body.data)
    table = await uploads.table(who, filename, content)
    await platform.log_action(who.uid, "attachments.table", f"Attached '{filename}' ({len(content):,} bytes) as a table")
    return _table_out(table, filename)


@router.post("/pdf")
async def attachment_pdf(body: FileIn, who: Requester = Depends(current_requester),
                         uploads: ArmoryUploads = Depends(get_uploads),
                         platform: PortcullisClient = Depends(get_platform)) -> PdfOut:
    """Keep the original for the PDF tools; extracted text is an optional preview."""
    filename = _name(body.filename)
    if not filename.lower().endswith(_PDF_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a PDF or supported image")
    content = _decode(body.data)
    uploaded = await uploads.pdf(who, filename, content)
    text, chars, truncated = "", 0, False
    if filename.lower().endswith(".pdf"):
        try:
            extracted = await extract_text_async(filename, content)
            text, chars, truncated = extracted.text, extracted.char_count, extracted.truncated
        except ExtractionError:
            pass  # Scans and blank pages remain valid inputs for inspect and merge.
    await platform.log_action(who.uid, "attachments.pdf", f"Attached '{filename}' ({len(content):,} bytes) for PDF tools")
    return PdfOut(filename=filename, file_id=uploaded["file_id"], pages=uploaded["pages"], kind=uploaded["kind"],
                  expires_at=uploaded["expires_at"], text=text, char_count=chars, truncated=truncated)


@router.post("/audio")
async def attachment_audio(body: AudioIn, who: Requester = Depends(current_requester),
                           connections: ToolServices = Depends(get_connections),
                           platform: PortcullisClient = Depends(get_platform)) -> AudioOut:
    """Keep the original for Scribe's transcribe tool; the agent gets the file_id."""
    filename, content = _audio(body)
    uploaded = await connections.post_file("/connections/scribe/files", filename, content)
    await platform.log_action(who.uid, "attachments.audio", f"Attached '{filename}' ({len(content):,} bytes) for transcription")
    return AudioOut(filename=filename, file_id=uploaded["file_id"], duration_s=float(uploaded["duration_s"]),
                    expires_at=float(uploaded["expires_at"]))


@router.post("/document")
async def attachment_document(body: DocumentIn, who: Requester = Depends(current_requester),
                              connections: ToolServices = Depends(get_connections),
                              platform: PortcullisClient = Depends(get_platform)) -> DocumentOut:
    """Read an image or PDF with Reader because the user asked."""
    filename = _name(body.filename)
    suffix = PurePosixPath(filename.lower()).suffix
    if suffix not in _DOCUMENT_SUFFIXES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a pdf, png, jpg, jpeg or webp file")
    content = _decode(body.data, _MAX_DOCUMENT_BYTES, "The document is larger than 20 MB")
    found = await read_with_reader(connections, suffix, content)
    text, truncated = found or ("", False)
    outcome = "Read" if found else "Could not read"
    await platform.log_action(who.uid, "attachments.document",
                              f"{outcome} '{filename}' ({len(content):,} bytes) with Reader")
    return DocumentOut(filename=filename, text=text, char_count=len(text), truncated=truncated,
                       read="reader" if found else "pages")


@router.post("/dictate")
async def dictate(body: AudioIn, who: Requester = Depends(current_requester),
                  connections: ToolServices = Depends(get_connections),
                  platform: PortcullisClient = Depends(get_platform)) -> DictationOut:
    """Speech as draft text, without asking the chat agent to transcribe it. The log never holds the words."""
    filename, content = _audio(body)
    result = await connections.post_file("/connections/scribe/transcribe", filename, content)
    await platform.log_action(who.uid, "attachments.dictate", f"Transcribed {len(content):,} bytes of dictated audio")
    return DictationOut(text=result["text"], duration_s=float(result["duration_s"]))


@router.post("/dictate/partial")
async def dictate_partial(body: AudioIn, who: Requester = Depends(current_requester),
                          connections: ToolServices = Depends(get_connections)) -> DictationOut:
    """A transient preview of a recording so far: no uploaded file and no log line."""
    filename, content = _audio(body)
    result = await connections.post_file("/connections/scribe/transcribe-partial", filename, content)
    return DictationOut(text=result["text"], duration_s=float(result["duration_s"]))
