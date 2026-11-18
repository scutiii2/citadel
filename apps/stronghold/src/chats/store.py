"""Chat history, folders and search, kept in Treasury.

Three collections, one document per record, keyed `<owner uid>:<id>`:
`chats` holds a chat's details (title, folder, pin, times), `chat_messages` its transcript, and
`chat_folders` a folder. The details are kept apart so the sidebar list never reads a transcript.
Every lookup is under the owner's uid, so another account's id behaves like a missing one.
Deleting chats revokes their share links first (the links live in `ShareStore`): if that fails,
nothing is deleted, so a deleted chat never keeps a working link.
"""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from src.clock import utcnow
from src.schema.models import ChatDoc, ChatFolderDoc, ChatMessagesDoc, checked
from src.document_store import DocumentStore
from src.shares.store import ShareStore

CHATS = "chats"
MESSAGES = "chat_messages"
FOLDERS = "chat_folders"

MAX_CHAT_BYTES = 2 * 1024 * 1024
MAX_CHATS_PER_ACCOUNT = 1000
MAX_FOLDERS_PER_ACCOUNT = 30
TITLE_MAX = 120
_PAGE = 500
_SCAN_PAGE = 25
_PURGE_MAX_PAGES = 200

MIN_QUERY_CHARS = 2
MAX_QUERY_CHARS = 100
MAX_HITS = 50
# Characters of context kept before and after the match in a snippet.
SNIPPET_BEFORE = 40
SNIPPET_AFTER = 90
# A question's attached files travel inside its text; their bodies are not what someone
# remembers typing, so they are left out of the search.
_ATTACHMENT = re.compile(r"\[\[ATTACHMENT [^\]]*\]\]\n[\s\S]*?\n\[\[/ATTACHMENT\]\]")
_SPACES = re.compile(r"\s+")

ChatMessage = dict[str, Any]


class ChatNotFound(Exception):
    """Unknown id, or another account's (deliberately indistinguishable)."""


class ChatLimitError(Exception):
    """A chat too large, or too many chats (maps to 413)."""


class NotABranchPoint(Exception):
    """The message a branch should end on is missing, or is not a plain answer."""


class FolderNotFound(Exception):
    """Unknown id, or another account's."""


class FolderLimitError(Exception):
    """Too many folders (maps to 409)."""


class FolderNameTaken(Exception):
    """Another folder of this account already has the name, ignoring case."""


class FolderBusy(Exception):
    """A chat in the folder has an answer being written (maps to 409)."""


def _key(owner: str, ident: str | int) -> str:
    return f"{owner}:{ident}"


def _now() -> str:
    return utcnow().isoformat()


def _encode(messages: list[ChatMessage]) -> None:
    if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > MAX_CHAT_BYTES:
        raise ChatLimitError(f"Chat is larger than {MAX_CHAT_BYTES // (1024 * 1024)} MB")


def _details(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: doc[k] for k in ("chat_id", "title", "agent_id", "message_count", "folder_id", "pinned",
                                "save_to_second_brain", "second_brain_scope", "created_at", "updated_at")}


def _snippet(text: str, start: int, length: int) -> dict[str, Any]:
    """`text` reduced to one line around the match, with ellipses at cut ends."""
    first = max(0, start - SNIPPET_BEFORE)
    end = min(len(text), start + length + SNIPPET_AFTER)
    before = _SPACES.sub(" ", text[first:start])
    matched = _SPACES.sub(" ", text[start:start + length])
    after = _SPACES.sub(" ", text[start + length:end])
    lead = ("…" if first > 0 else "") + before
    suffix = "…" if end < len(text) else ""
    return {"text": f"{lead}{matched}{after}{suffix}", "start": len(lead), "length": len(matched)}


def _match(details: dict[str, Any], messages: list[ChatMessage], pattern: re.Pattern[str]) -> dict[str, Any] | None:
    found = pattern.search(details["title"])
    title_match = {"start": found.start(), "length": found.end() - found.start()} if found else None
    first: tuple[int, dict[str, Any]] | None = None
    count = 0
    for index, message in enumerate(messages):
        text = _ATTACHMENT.sub(" ", message.get("content", ""))
        found = pattern.search(text)
        if found is None:
            continue
        count += 1
        if first is None:
            first = (index, _snippet(text, found.start(), found.end() - found.start()))
    if title_match is None and first is None:
        return None
    return {"id": details["chat_id"], "folder_id": details["folder_id"], "title": details["title"],
            "updated_at": details["updated_at"], "title_match": title_match,
            "snippet": first[1] if first else None, "message_index": first[0] if first else None,
            "message_matches": count}


class ChatStore:
    def __init__(self, store: DocumentStore, shares: ShareStore) -> None:
        self._store = store
        self._shares = shares

    # --- reading ---------------------------------------------------------------------------

    async def _all(self, collection: str, owner: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        while True:
            page = await self._store.query(collection, {"owner": owner}, limit=_PAGE, offset=len(docs))
            docs += page
            if len(page) < _PAGE:
                return docs

    async def list(self, owner: str) -> list[dict[str, Any]]:
        """Newest first, without transcripts."""
        docs = await self._all(CHATS, owner)
        return [_details(d) for d in sorted(docs, key=lambda d: (d["updated_at"], d["created_at"]), reverse=True)]

    async def get(self, owner: str, chat_id: str) -> dict[str, Any]:
        doc = await self._store.get(CHATS, _key(owner, chat_id))
        body = await self._store.get(MESSAGES, _key(owner, chat_id)) if doc else None
        if doc is None:
            raise ChatNotFound(chat_id)
        return {**_details(doc), "messages": body["messages"] if body else []}

    # --- writing ---------------------------------------------------------------------------

    async def put(self, owner: str, chat_id: str, title: str, agent_id: str | None,
                  messages: list[ChatMessage]) -> dict[str, Any]:
        """Creates the chat or replaces its title, agent and transcript."""
        _encode(messages)
        key = _key(owner, chat_id)
        doc = await self._store.get(CHATS, key)
        now = _now()
        if doc is None:
            if len(await self._all(CHATS, owner)) + 1 > MAX_CHATS_PER_ACCOUNT:
                raise ChatLimitError(f"At most {MAX_CHATS_PER_ACCOUNT} chats per account - delete some first")
            doc = {"key": key, "owner": owner, "chat_id": chat_id, "folder_id": None, "pinned": False,
                   "save_to_second_brain": False, "second_brain_scope": "instance", "created_at": now}
        doc.update(title=title, agent_id=agent_id, message_count=len(messages), updated_at=now)
        await self._save(doc, messages)
        return {**_details(doc), "messages": messages}

    async def _save(self, doc: dict[str, Any], messages: list[ChatMessage] | None = None) -> None:
        if messages is not None:
            await self._store.put(MESSAGES, doc["key"], checked(ChatMessagesDoc, {
                "key": doc["key"], "owner": doc["owner"], "chat_id": doc["chat_id"], "messages": messages}))
        await self._store.put(CHATS, doc["key"], checked(ChatDoc, doc))

    async def replace_messages(self, owner: str, chat_id: str, messages: list[ChatMessage],
                               agent_id: str | None = None) -> dict[str, Any]:
        """New transcript for an existing chat, keeping its title (and its agent unless one is given)."""
        doc = await self._doc(owner, chat_id)
        _encode(messages)
        doc.update(message_count=len(messages), updated_at=_now())
        if agent_id is not None:
            doc["agent_id"] = agent_id
        await self._save(doc, messages)
        return {**_details(doc), "messages": messages}

    async def update(self, owner: str, chat_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Title, folder (None takes it out; another account's folder is FolderNotFound), pin and the
        second-brain settings. Filing a chat is not activity: updated_at stays."""
        doc = await self._doc(owner, chat_id)
        if "folder_id" in changes:
            folder_id = changes["folder_id"]
            if folder_id is not None and await self._store.get(FOLDERS, _key(owner, folder_id)) is None:
                raise FolderNotFound(folder_id)
            doc["folder_id"] = folder_id
        for field in ("title", "pinned", "save_to_second_brain", "second_brain_scope"):
            if changes.get(field) is not None:
                doc[field] = changes[field]
        await self._save(doc)
        return _details(doc)

    async def branch(self, owner: str, source_id: str, upto: int) -> dict[str, Any]:
        """A new chat holding the source's messages up to and including answer `upto`, which must be one of
        the assistant's plain answers. It keeps the source's agent and folder (never its pin)."""
        source = await self.get(owner, source_id)
        messages = source["messages"]
        target = messages[upto] if 0 <= upto < len(messages) else None
        if target is None or target.get("role") != "assistant" or target.get("kind"):
            raise NotABranchPoint(upto)
        title = f"Branch of {source['title']}"
        if len(title) > TITLE_MAX:
            title = title[:TITLE_MAX - 1] + "…"
        branched = await self.put(owner, str(uuid.uuid4()), title, source["agent_id"], messages[:upto + 1])
        if source["folder_id"] is not None:
            await self.update(owner, branched["chat_id"], {"folder_id": source["folder_id"]})
            branched["folder_id"] = source["folder_id"]
        return branched

    async def _doc(self, owner: str, chat_id: str) -> dict[str, Any]:
        doc = await self._store.get(CHATS, _key(owner, chat_id))
        if doc is None:
            raise ChatNotFound(chat_id)
        return doc

    # --- deleting --------------------------------------------------------------------------

    async def _remove(self, owner: str, chat_ids: list[str]) -> None:
        await self._shares.revoke_chats(owner, chat_ids)  # first: if this fails nothing is deleted
        for chat_id in chat_ids:
            await self._store.delete(MESSAGES, _key(owner, chat_id))
            await self._store.delete(CHATS, _key(owner, chat_id))

    async def delete(self, owner: str, chat_id: str) -> None:
        await self._doc(owner, chat_id)
        await self._remove(owner, [chat_id])

    async def delete_all(self, owner: str) -> int:
        chat_ids = [d["chat_id"] for d in await self._all(CHATS, owner)]
        await self._remove(owner, chat_ids)
        return len(chat_ids)

    async def purge_owner(self, owner: str) -> None:
        """Everything a deleted account kept: chats, transcripts and folders (its share links go with its
        shares purge)."""
        for collection in (MESSAGES, CHATS, FOLDERS):
            for _ in range(_PURGE_MAX_PAGES):
                docs = await self._store.query(collection, {"owner": owner}, limit=_PAGE)
                if not docs:
                    break
                for doc in docs:
                    await self._store.delete(collection, doc["key"])

    # --- search ----------------------------------------------------------------------------

    async def search(self, owner: str, query: str, limit: int = MAX_HITS) -> list[dict[str, Any]]:
        """Chats whose title or messages contain `query` (case-insensitive, literal), newest first."""
        needle = query.strip()
        if len(needle) < MIN_QUERY_CHARS:
            return []
        pattern = re.compile(re.escape(needle), re.IGNORECASE)
        details = {d["chat_id"]: _details(d) for d in await self._all(CHATS, owner)}
        hits: list[dict[str, Any]] = []
        offset = 0
        while True:  # transcripts a few at a time: a big history is never held whole
            page = await self._store.query(MESSAGES, {"owner": owner}, limit=_SCAN_PAGE, offset=offset)
            for doc in page:
                chat = details.get(doc["chat_id"])
                hit = _match(chat, doc["messages"], pattern) if chat else None
                if hit is not None:
                    hits.append(hit)
            if len(page) < _SCAN_PAGE:
                break
            offset += _SCAN_PAGE
        hits.sort(key=lambda h: h["updated_at"], reverse=True)
        return hits[:limit]

    # --- folders ---------------------------------------------------------------------------

    async def folders(self, owner: str) -> list[dict[str, Any]]:
        """In display order (position, then id), each with its chat count."""
        counts: dict[int, int] = {}
        for chat in await self._all(CHATS, owner):
            if chat["folder_id"] is not None:
                counts[chat["folder_id"]] = counts.get(chat["folder_id"], 0) + 1
        docs = sorted(await self._all(FOLDERS, owner), key=lambda d: (d["position"], d["id"]))
        return [{"id": d["id"], "name": d["name"], "position": d["position"], "chat_count": counts.get(d["id"], 0)}
                for d in docs]

    async def _folder(self, owner: str, folder_id: int) -> dict[str, Any]:
        doc = await self._store.get(FOLDERS, _key(owner, folder_id))
        if doc is None:
            raise FolderNotFound(folder_id)
        return doc

    async def _name_free(self, owner: str, name: str, except_id: int | None) -> None:
        for doc in await self._all(FOLDERS, owner):
            if doc["id"] != except_id and doc["name"].lower() == name.lower():
                raise FolderNameTaken(name)

    async def create_folder(self, owner: str, name: str) -> dict[str, Any]:
        """Appended after the existing folders."""
        existing = await self._all(FOLDERS, owner)
        if len(existing) >= MAX_FOLDERS_PER_ACCOUNT:
            raise FolderLimitError(f"At most {MAX_FOLDERS_PER_ACCOUNT} folders per account - delete some first")
        await self._name_free(owner, name, None)
        taken = {d["id"] for d in existing}
        folder_id = secrets.randbelow(2**31 - 1) + 1
        while folder_id in taken:
            folder_id = secrets.randbelow(2**31 - 1) + 1
        doc = {"key": _key(owner, folder_id), "owner": owner, "id": folder_id, "name": name,
               "position": max((d["position"] for d in existing), default=-1) + 1, "created_at": _now()}
        await self._store.put(FOLDERS, doc["key"], checked(ChatFolderDoc, doc))
        return {"id": folder_id, "name": name, "position": doc["position"], "chat_count": 0}

    async def rename_folder(self, owner: str, folder_id: int, name: str) -> dict[str, Any]:
        doc = await self._folder(owner, folder_id)
        await self._name_free(owner, name, folder_id)
        doc["name"] = name
        await self._store.put(FOLDERS, doc["key"], checked(ChatFolderDoc, doc))
        return doc

    async def reorder_folder(self, owner: str, folder_id: int, position: int) -> dict[str, Any]:
        doc = await self._folder(owner, folder_id)
        doc["position"] = position
        await self._store.put(FOLDERS, doc["key"], checked(ChatFolderDoc, doc))
        return doc

    async def move_folder(self, owner: str, folder_id: int, direction: str) -> dict[str, Any]:
        """Move one place in display order, renumbering every folder."""
        doc = await self._folder(owner, folder_id)
        ordered = sorted(await self._all(FOLDERS, owner), key=lambda d: (d["position"], d["id"]))
        index = next(i for i, item in enumerate(ordered) if item["id"] == folder_id)
        target = index + (-1 if direction == "up" else 1)
        if not 0 <= target < len(ordered):
            return doc
        ordered[index], ordered[target] = ordered[target], ordered[index]
        for position, item in enumerate(ordered):
            if item["position"] != position:
                item["position"] = position
                await self._store.put(FOLDERS, item["key"], checked(ChatFolderDoc, item))
        return next(item for item in ordered if item["id"] == folder_id)

    async def count_in_folder(self, owner: str, folder_id: int) -> int:
        return sum(1 for chat in await self._all(CHATS, owner) if chat["folder_id"] == folder_id)

    async def delete_folder(self, owner: str, folder_id: int, running: set[str]) -> tuple[str, int]:
        """Deletes the folder and every chat in it, revoking their links first. `running` holds this
        account's chat ids that have an answer being written: if any is in the folder nothing is deleted
        (FolderBusy). Returns (folder name, chats deleted)."""
        doc = await self._folder(owner, folder_id)
        chat_ids = [c["chat_id"] for c in await self._all(CHATS, owner) if c["folder_id"] == folder_id]
        if running.intersection(chat_ids):
            raise FolderBusy(folder_id)
        await self._remove(owner, chat_ids)
        await self._store.delete(FOLDERS, doc["key"])
        return doc["name"], len(chat_ids)


def message_time() -> str:
    """Now as the "at" of a message: ISO 8601 UTC with milliseconds."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
