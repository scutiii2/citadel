"""Long-term memory: Markdown files in a confined folder, one subfolder per account.

<root>/accounts/<uid>/[folder/]<slug>-<id8>.md is a record; <root>/accounts/<uid>/.originals/<id>.md keeps the text an
agent or a share wrote before the user first edited it. Every path is built here from a validated uid, a validated
folder and a generated file name, and is checked to resolve inside the account folder before it is touched. Disk work
runs in a thread and each account has one lock, so writes cannot interleave and the quotas cannot be raced.
The file list and the search index live in memory per account and are reloaded after `refresh_seconds`, so a file
dropped into the folder by hand shows up within that time (shortcut: one process owns the folder; upgrade to a watcher
if several Stronghold processes ever share it).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from src.brain.limits import LONG_TERM_RANGES, LongTermLimits
from src.brain.records import EDITORS, TITLE_MAX, Record, RecordError, clean_folder, parse, path_id, render, reserved_name, slug
from src.brain.search import Bm25Index, make_snippet
from src.clock import utcnow
from src.notes.store import normalize_tags

ORIGINALS = ".originals"
_UID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_ORIGINAL = re.compile(r"[0-9a-f]{32}\.md")
_MAX_STORED_BYTES = LONG_TERM_RANGES["max_record_chars"][1] * 4 + 4096


class BrainError(Exception):
    """A refused brain change; `status` is the HTTP code the REST routes answer. The message never holds file text."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Hit:
    record: Record
    score: float
    snippet: str


@dataclass
class _Entry:
    record: Record
    path: Path
    size: int


class _Account:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.entries: dict[str, _Entry] = {}
        self.original_sizes: dict[str, int] = {}
        self.purged = False
        self.loaded_at: float | None = None
        self.skipped = 0
        self.index: Bm25Index | None = None


def _now() -> str:
    return utcnow().isoformat(timespec="seconds")


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _inside(base: Path, path: Path) -> bool:
    real_base, real = os.path.realpath(base), os.path.realpath(path)
    try:
        return os.path.commonpath([real_base, real]) == real_base
    except ValueError:  # another drive
        return False


def _confine(root: Path, home: Path, path: Path) -> None:
    # Resolving inside the root is insufficient: an account link could point at another account.
    expected_home = Path(os.path.realpath(root)) / "accounts" / home.name
    if Path(os.path.realpath(home)) != expected_home or not _inside(home, path):
        raise BrainError(403, "That path is outside the brain.")


def _walk_error(error: OSError) -> None:
    raise error


def _has_home(root: Path, home: Path) -> bool:
    _confine(root, home, home)
    try:
        if not stat.S_ISDIR(root.stat().st_mode) or not stat.S_ISDIR(home.stat().st_mode):
            raise NotADirectoryError
    except FileNotFoundError:
        # A new folder is normal. An unavailable drive or UNC share is a storage error.
        Path(root.absolute().anchor).stat()
        return False
    return True


def _original_sizes(home: Path) -> dict[str, int]:
    folder = home / ORIGINALS
    sizes: dict[str, int] = {}
    if not _inside(home, folder) or folder.is_symlink():
        return sizes
    try:
        with os.scandir(folder) as children:
            for child in children:
                if _ORIGINAL.fullmatch(child.name) and _inside(home, Path(child.path)):
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode):
                        sizes[child.name.removesuffix(".md")] = info.st_size
    except FileNotFoundError:
        pass
    return sizes


def _scan(root: Path, home: Path) -> tuple[dict[str, _Entry], dict[str, int], int]:
    entries: dict[str, _Entry] = {}
    skipped = 0
    if not _has_home(root, home):
        return entries, {}, 0
    for current, dirs, names in os.walk(home, followlinks=False, onerror=_walk_error):
        directory = Path(current)
        resolved = directory.resolve()
        # Compare resolved locations to skip Windows junctions and aliases on Python 3.11 too.
        dirs[:] = sorted(
            name for name in dirs
            if not name.startswith(".")
            and not (directory / name).is_symlink()
            and (directory / name).resolve() == resolved / name
        )
        relative = directory.relative_to(home).as_posix()
        try:
            folder = clean_folder("" if relative == "." else relative)
        except RecordError:
            skipped += len(names)
            dirs[:] = []
            continue
        for name in sorted(names):
            path = directory / name
            if not name.endswith(".md") or name.startswith(".") or path.is_symlink():
                continue
            try:
                _confine(root, home, path)
                info = path.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_STORED_BYTES:
                    raise RecordError("too large")
                record = parse(path.read_text(encoding="utf-8"), folder=folder, fallback_id=path_id(f"{folder}/{name}"),
                               fallback_title=path.stem, fallback_time=_stamp(info.st_mtime))
            except (BrainError, FileNotFoundError, UnicodeError, RecordError):
                skipped += 1
                continue
            if record.id in entries:
                skipped += 1
                continue
            entries[record.id] = _Entry(record, path, info.st_size)
    return entries, _original_sizes(home), skipped


def _write(root: Path, home: Path, path: Path, text: str) -> None:
    _confine(root, home, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _confine(root, home, path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".brain-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(text.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _create_record(root: Path, home: Path, path: Path, text: str) -> None:
    _confine(root, home, path)
    if os.path.lexists(path):
        raise BrainError(409, "A file already exists at that location.")
    _write(root, home, path, text)


def _remove(root: Path, home: Path, path: Path) -> None:
    _confine(root, home, path)
    path.unlink(missing_ok=True)
    parent = path.parent
    try:
        while parent != home and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    except OSError:
        pass


def _save_change(root: Path, home: Path, previous: Path, target: Path, text: str,
                 original: tuple[Path, str] | None) -> None:
    _confine(root, home, previous)
    _confine(root, home, target)
    moving = target != previous
    if moving and os.path.lexists(target):
        raise BrainError(409, "A file already exists at that location.")
    if original is not None:
        _write(root, home, *original)
    try:
        _write(root, home, target, text)
        if moving:
            try:
                _remove(root, home, previous)
            except OSError:
                _remove(root, home, target)
                raise
    except OSError:
        if original is not None:
            _remove(root, home, original[0])
        raise


def _read_original(root: Path, home: Path, path: Path, record: Record) -> Record:
    _confine(root, home, path)
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_STORED_BYTES:
            raise BrainError(409, "The original cannot be read.")
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise BrainError(409, "There is nothing to revert.") from None
    except UnicodeError:
        raise BrainError(409, "The original cannot be read.") from None
    try:
        original = parse(text, folder=record.folder, fallback_id=record.id,
                         fallback_title=record.title, fallback_time=record.updated_at)
    except RecordError:
        raise BrainError(409, "The original cannot be read.") from None
    if original.id != record.id:
        raise BrainError(409, "The original cannot be read.")
    return original


def _delete_record(root: Path, home: Path, active: Path | None, original: Path) -> None:
    _confine(root, home, original)
    if active is not None:
        _remove(root, home, active)
    _remove(root, home, original)


def _purge(root: Path, home: Path) -> None:
    if _has_home(root, home):
        shutil.rmtree(home)


def _used_bytes(account: _Account) -> int:
    return sum(entry.size for entry in account.entries.values()) + sum(account.original_sizes.values())


def _entry(account: _Account, file_id: object) -> _Entry:
    entry = account.entries.get(file_id) if isinstance(file_id, str) else None
    if entry is None:
        raise BrainError(404, "No such file.")
    return entry


class BrainFiles:
    def __init__(self, root: Path, limits: LongTermLimits, *, refresh_seconds: float = 30.0,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self._root = Path(root)
        self.limits = limits
        self._refresh = refresh_seconds
        self._monotonic = monotonic
        self._accounts: dict[str, _Account] = {}

    def _home(self, uid: object) -> Path:
        if not isinstance(uid, str) or not _UID.fullmatch(uid) or reserved_name(uid):
            raise BrainError(400, "Invalid account.")
        return self._root / "accounts" / uid

    @asynccontextmanager
    async def _open(self, uid: object):
        home = self._home(uid)
        account = self._accounts.setdefault(uid, _Account())
        async with account.lock:
            now = self._monotonic()
            if not account.purged and (account.loaded_at is None or now - account.loaded_at >= self._refresh):
                scanned = await asyncio.to_thread(_scan, self._root, home)
                account.entries, account.original_sizes, account.skipped = scanned
                account.loaded_at, account.index = now, None
            yield home, account

    async def _mutate(self, account: _Account, operation: Callable, *args) -> None:
        # Keep the account lock until disk work ends, even if its request was cancelled.
        work = asyncio.create_task(asyncio.to_thread(operation, *args))
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            account.loaded_at = None
            await work
            raise
        except (OSError, BrainError):
            account.loaded_at = None
            raise

    @property
    def root(self) -> Path:
        return self._root

    @asynccontextmanager
    async def locked(self, uid: object):
        """The account lock and folder for work that bypasses the note index (skills).
        A purged account (deleted while an agent still held its token) is refused."""
        home = self._home(uid)
        account = self._accounts.setdefault(uid, _Account())
        async with account.lock:
            if account.purged:
                raise BrainError(404, "No such account.")
            yield home, account

    async def mutate(self, account: _Account, operation: Callable, *args) -> None:
        """Run disk work in a thread while holding the lock `locked` gave out (same rules as note writes)."""
        await self._mutate(account, operation, *args)

    def _check(self, title: str, body: str, tags: Iterable[str], folder: str) -> tuple[str, str, tuple[str, ...], str]:
        title = str(title).strip()
        if not title or len(title) > TITLE_MAX:
            raise BrainError(422, f"A title is 1 to {TITLE_MAX} characters.")
        if len(body) > self.limits.max_record_chars:
            raise BrainError(422, f"A file holds at most {self.limits.max_record_chars} characters.")
        try:
            title.encode("utf-8")
            body.encode("utf-8")
            return title, body, tuple(normalize_tags(list(tags))), clean_folder(folder)
        except UnicodeError:
            raise BrainError(422, "File text must be valid UTF-8.") from None
        except ValueError as error:
            raise BrainError(422, str(error)) from None

    def _room(self, account: _Account, extra_bytes: int, new_file: bool) -> None:
        if new_file and len(account.entries) >= self.limits.max_files:
            raise BrainError(409, f"You have reached the limit of {self.limits.max_files} files.")
        if extra_bytes > 0 and _used_bytes(account) + extra_bytes > self.limits.max_total_bytes:
            raise BrainError(409, "Your long-term memory is full.")

    async def list(self, uid: str, folder: str | None = None) -> list[Record]:
        try:
            wanted = None if folder is None else clean_folder(folder)
        except RecordError as error:
            raise BrainError(422, str(error)) from None
        async with self._open(uid) as (_, account):
            found = [e.record for e in account.entries.values() if wanted is None or e.record.folder == wanted]
        return sorted(found, key=lambda record: record.updated_at, reverse=True)

    async def folders(self, uid: str) -> list[str]:
        async with self._open(uid) as (_, account):
            found: set[str] = set()
            for entry in account.entries.values():
                parts = entry.record.folder.split("/") if entry.record.folder else []
                found.update("/".join(parts[:count]) for count in range(1, len(parts) + 1))
        return sorted(found)

    async def get(self, uid: str, file_id: str) -> Record:
        async with self._open(uid) as (_, account):
            return _entry(account, file_id).record

    async def search(self, uid: str, query: str, limit: int | None = None) -> list[Hit]:
        async with self._open(uid) as (_, account):
            wanted = max(1, min(limit or self.limits.search_limit, 30))
            if account.index is None:
                documents = {i: (e.record.title, e.record.body, " ".join(e.record.tags)) for i, e in account.entries.items()}
                account.index = await asyncio.to_thread(Bm25Index, documents)
            ranked = await asyncio.to_thread(account.index.search, query, None)
            records = {doc_id: account.entries[doc_id].record for doc_id, _ in ranked}
        ranked.sort(key=lambda pair: records[pair[0]].updated_at, reverse=True)
        ranked.sort(key=lambda pair: -pair[1])  # stable: a tie keeps the newest file first
        return [Hit(records[doc_id], score, make_snippet(records[doc_id].body, query)) for doc_id, score in ranked[:wanted]]

    async def create(self, uid: str, *, title: str, body: str, tags: Iterable[str] = (), folder: str = "",
                     actor: str = "user", shared_from: str = "") -> Record:
        if actor not in EDITORS:
            raise BrainError(400, "Unknown editor.")
        if shared_from and actor != "user":
            raise BrainError(400, "Only a person imports a shared file.")
        title, body, tag_tuple, folder = self._check(title, body, tags, folder)
        async with self._open(uid) as (home, account):
            if account.purged:
                raise BrainError(404, "No such account.")
            now = _now()
            source = "manual" if actor == "user" else "automatic"
            record = Record(uuid.uuid4().hex, title, body, folder, tag_tuple, "shared" if shared_from else source,
                            actor, False, False, 1, now, now, shared_from)
            text = render(record)
            size = len(text.encode("utf-8"))
            self._room(account, size, True)
            if record.id in account.entries or record.id in account.original_sizes:
                raise BrainError(409, "A file already exists with that id.")
            path = home / folder / f"{slug(title)}-{record.id[:8]}.md"
            await self._mutate(account, _create_record, self._root, home, path, text)
            account.entries[record.id] = _Entry(record, path, size)
            account.index = None
            return record

    async def update(self, uid: str, file_id: str, *, actor: str = "user", title: str | None = None, body: str | None = None,
                     tags: Iterable[str] | None = None, folder: str | None = None, agent_editable: bool | None = None,
                     expected_revision: int | None = None) -> Record:
        if actor not in EDITORS:
            raise BrainError(400, "Unknown editor.")
        if all(value is None for value in (title, body, tags, folder, agent_editable)):
            raise BrainError(422, "Nothing to change.")
        async with self._open(uid) as (home, account):
            entry = _entry(account, file_id)
            old = entry.record
            if expected_revision is not None and expected_revision != old.revision:
                raise BrainError(412, "This file changed since you opened it.")
            if actor == "agent":
                if folder is not None or agent_editable is not None:
                    raise BrainError(403, "Agents cannot move files or change who may edit them.")
                if old.source == "shared" or (old.source != "automatic" and not old.agent_editable):
                    raise BrainError(403, "This file belongs to the user and is read-only for agents.")
            new_title, new_body, new_tags, new_folder = self._check(
                old.title if title is None else title, old.body if body is None else body,
                old.tags if tags is None else tags, old.folder if folder is None else folder)
            changed = (new_title, new_body, new_tags) != (old.title, old.body, old.tags)
            keep_original = actor == "user" and changed and old.source != "manual" and not old.edited
            record = replace(
                old, title=new_title, body=new_body, tags=new_tags, folder=new_folder,
                agent_editable=old.agent_editable if agent_editable is None else bool(agent_editable),
                edited=old.edited or keep_original, last_editor=actor if changed else old.last_editor,
                revision=old.revision + 1, updated_at=_now())
            text = render(record)
            size = len(text.encode("utf-8"))
            original = (home / ORIGINALS / f"{old.id}.md", render(old)) if keep_original else None
            original_size = len(original[1].encode("utf-8")) if original is not None else 0
            original_delta = original_size - account.original_sizes.get(old.id, 0) if original is not None else 0
            self._room(account, size - entry.size + original_delta, False)
            path = entry.path if new_folder == old.folder else home / new_folder / entry.path.name
            await self._mutate(account, _save_change, self._root, home, entry.path, path, text, original)
            if original is not None:
                account.original_sizes[old.id] = original_size
            account.entries[record.id] = _Entry(record, path, size)
            account.index = None
            return record

    async def revert(self, uid: str, file_id: str, *, expected_revision: int | None = None) -> Record:
        async with self._open(uid) as (home, account):
            entry = _entry(account, file_id)
            old = entry.record
            if expected_revision is not None and expected_revision != old.revision:
                raise BrainError(412, "This file changed since you opened it.")
            original_path = home / ORIGINALS / f"{old.id}.md"
            if not old.edited:
                raise BrainError(409, "There is nothing to revert.")
            original = await asyncio.to_thread(_read_original, self._root, home, original_path, old)
            record = replace(old, title=original.title, body=original.body, tags=original.tags, edited=False,
                             last_editor=original.last_editor, revision=old.revision + 1, updated_at=_now())
            text = render(record)
            size = len(text.encode("utf-8"))
            self._room(account, size - entry.size - account.original_sizes.get(old.id, 0), False)
            await self._mutate(account, _write, self._root, home, entry.path, text)
            await self._mutate(account, _remove, self._root, home, original_path)
            account.original_sizes.pop(old.id, None)
            account.entries[record.id] = _Entry(record, entry.path, size)
            account.index = None
            return record

    async def delete(self, uid: str, file_id: str) -> None:
        async with self._open(uid) as (home, account):
            entry = account.entries.get(file_id)
            if entry is None and file_id not in account.original_sizes:
                raise BrainError(404, "No such file.")
            active = entry.path if entry is not None else None
            original = home / ORIGINALS / f"{file_id}.md"
            await self._mutate(account, _delete_record, self._root, home, active, original)
            account.entries.pop(file_id, None)
            account.original_sizes.pop(file_id, None)
            account.index = None

    async def summary(self, uid: str) -> dict[str, int]:
        async with self._open(uid) as (_, account):
            return {"files": len(account.entries), "bytes": _used_bytes(account),
                    "skipped": account.skipped, "max_files": self.limits.max_files,
                    "max_total_bytes": self.limits.max_total_bytes, "max_record_chars": self.limits.max_record_chars}

    async def purge(self, uid: str) -> None:
        home = self._home(uid)
        account = self._accounts.setdefault(uid, _Account())
        async with account.lock:
            # In-flight agents may still carry a signed requester for the deleted uid.
            account.purged = True
            account.entries.clear()
            account.original_sizes.clear()
            account.loaded_at, account.index, account.skipped = None, None, 0
            await self._mutate(account, _purge, self._root, home)
