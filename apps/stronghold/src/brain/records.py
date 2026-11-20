"""A long-term memory record: one Markdown file with a small header.

    ---
    id: "<32 hex>"
    title: "Tea notes"
    tags: ["tea"]
    ...
    ---

    The body, as Markdown.

Each header value is JSON, so a title may hold any character and the header needs no YAML library.
A file with no header at all is a plain Markdown file the user dropped in; it is adopted as a manual record.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import re
from dataclasses import dataclass
from pathlib import PureWindowsPath

from src.notes.store import normalize_tags

TITLE_MAX = 200
SOURCES = ("manual", "automatic", "shared")
EDITORS = ("user", "agent")
MAX_DEPTH = 3
_FENCE = "---"
_ID = re.compile(r"[0-9a-f]{32}")
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


class RecordError(ValueError):
    """A header or a folder is unusable; the message is safe to show (it never holds file text)."""


@dataclass(frozen=True)
class Record:
    id: str
    title: str
    body: str
    folder: str = ""
    tags: tuple[str, ...] = ()
    source: str = "manual"
    last_editor: str = "user"
    agent_editable: bool = False
    edited: bool = False
    revision: int = 1
    created_at: str = ""
    updated_at: str = ""


def reserved_name(name: str) -> bool:
    """Use the Windows filename rules on every platform, including Python 3.12."""
    check = getattr(ntpath, "isreserved", None)
    return check(name) if check is not None else PureWindowsPath(name).is_reserved()


def clean_folder(raw: str) -> str:
    """Normalize up to three relative folder segments inside an account."""
    text = raw.strip()
    if text.startswith("/") and not text.endswith("/"):
        raise RecordError("A folder must be relative to the brain.")
    text = text.strip("/")
    if not text:
        return ""
    segments = text.split("/")
    if len(segments) > MAX_DEPTH or not all(
        _SEGMENT.fullmatch(part) and not reserved_name(part) for part in segments
    ):
        raise RecordError(f"A folder is up to {MAX_DEPTH} levels of lowercase letters, digits, - and _ (40 characters each).")
    return "/".join(segments)


def slug(title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return words or "note"


def path_id(relative_path: str) -> str:
    """The id of a file that has no header yet: stable for its path, so a first save keeps it."""
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:32]


def render(record: Record) -> str:
    header = {
        "id": record.id, "title": record.title, "tags": list(record.tags), "source": record.source,
        "last_editor": record.last_editor, "agent_editable": record.agent_editable, "edited": record.edited,
        "revision": record.revision, "created_at": record.created_at, "updated_at": record.updated_at,
    }
    lines = [_FENCE, *(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in header.items()), _FENCE, "", record.body]
    return "\n".join(lines) + "\n"


def _header_line(line: str) -> tuple[str, object]:
    key, separator, raw = line.partition(": ")
    if not separator or not key.isidentifier():
        raise RecordError("A header line is not `key: value`.")
    try:
        return key, json.loads(raw)
    except ValueError:
        raise RecordError("A header value is not JSON.") from None


def parse(text: str, *, folder: str, fallback_id: str, fallback_title: str, fallback_time: str) -> Record:
    text = text.replace("\r\n", "\n")
    if not text.startswith(_FENCE + "\n"):
        return Record(fallback_id, fallback_title[:TITLE_MAX] or "note", text, folder,
                      created_at=fallback_time, updated_at=fallback_time)
    head, closed, rest = text[len(_FENCE) + 1:].partition("\n" + _FENCE + "\n")
    if not closed:
        raise RecordError("The header is not closed.")
    values = dict(_header_line(line) for line in head.split("\n") if line)
    body = rest[1:] if rest.startswith("\n") else rest
    body = body[:-1] if body.endswith("\n") else body

    def text_of(key: str, default: str = "") -> str:
        value = values.get(key, default)
        if not isinstance(value, str):
            raise RecordError(f"{key} must be text.")
        return value

    record_id = text_of("id")
    title = text_of("title").strip()
    if not _ID.fullmatch(record_id) or not title or len(title) > TITLE_MAX:
        raise RecordError("The header needs a valid id and title.")
    raw_tags = values.get("tags", [])
    if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
        raise RecordError("tags must be a list of text.")
    try:
        tags = tuple(normalize_tags(raw_tags))
    except ValueError:
        raise RecordError("A tag is not valid.") from None
    source, editor = text_of("source", "manual"), text_of("last_editor", "user")
    if source not in SOURCES or editor not in EDITORS:
        raise RecordError("Unknown source or editor.")
    flags = {name: values.get(name, False) for name in ("agent_editable", "edited")}
    revision = values.get("revision", 1)
    if not all(isinstance(flag, bool) for flag in flags.values()) or isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise RecordError("A flag or the revision is not valid.")
    return Record(record_id, title, body, folder, tags, source, editor, flags["agent_editable"], flags["edited"], revision,
                  text_of("created_at", fallback_time), text_of("updated_at", fallback_time))
