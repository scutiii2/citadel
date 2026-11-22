"""Portcullis's view of an account's chat history, which Stronghold keeps.

`ChatService` has the calls the routes and the turn engine use (list, get, put, replace_messages,
update, branch, delete) and asks Stronghold (`apps/stronghold/src/chats`) for each. Stronghold
checks the owner, so another account's chat id behaves exactly like a nonexistent one; it also
revokes a chat's share links before it deletes the chat. When Stronghold is down the call raises
StrongholdUnavailable (answered 502), so nothing is lost or half-done.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import HTTPException

from src.services.stronghold_forwarder import StrongholdForwarder

# Stronghold's limits (apps/stronghold/src/chats/store.py); kept here for the legacy chat_app importer.
MAX_CHAT_BYTES = 2 * 1024 * 1024
MAX_CHATS_PER_ACCOUNT = 1000
TITLE_MAX = 120
# "folder_id was not sent", as opposed to None ("take it out of its folder").
UNSET: Any = object()


class ChatNotFound(Exception):
    """Unknown id, or another account's (deliberately indistinguishable)."""


class FolderNotFound(Exception):
    """Unknown folder id, or another account's."""


class ChatLimitError(Exception):
    """A chat too large, or too many chats (maps to 413)."""


class NotABranchPoint(Exception):
    """The message a branch should end on is missing, or is not a plain
    answer (a question, summary, raw log or command result)."""


# {"role": "user" | "assistant", "content": str} plus optional "kind"
# ("summary", "log_attachment", "command", "triage"), "model", "total_tokens",
# "input_tokens", "output_tokens", "duration_s", "context_tokens",
# "context_window", "context_breakdown", "agent_usage", "at" (when it was written, UTC, see
# message_time) - validated by the route.
ChatMessage = dict[str, Any]


def message_time() -> str:
    """Now as the "at" of a message: ISO 8601 UTC with milliseconds, e.g.
    2026-10-06T14:03:09.123Z. Messages saved before this existed have none."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _encode(messages: list[ChatMessage]) -> str:
    text = json.dumps(messages, ensure_ascii=False)
    if len(text.encode("utf-8")) > MAX_CHAT_BYTES:
        raise ChatLimitError(f"Chat is larger than {MAX_CHAT_BYTES // (1024 * 1024)} MB")
    return text


@dataclass
class ChatRecord:
    """A chat as Stronghold answered. `messages` is None in a list: the sidebar never reads transcripts."""

    chat_id: str
    title: str
    agent_id: str | None
    message_count: int
    folder_id: int | None
    pinned: bool
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] | None = None

    @classmethod
    def of(cls, doc: dict[str, Any]) -> ChatRecord:
        return cls(
            chat_id=doc["chat_id"], title=doc["title"], agent_id=doc["agent_id"], message_count=doc["message_count"],
            folder_id=doc["folder_id"], pinned=doc["pinned"],
            created_at=datetime.fromisoformat(doc["created_at"]),
            updated_at=datetime.fromisoformat(doc["updated_at"]), messages=doc.get("messages"),
        )


def decode_messages(chat: ChatRecord) -> list[ChatMessage]:
    if chat.messages is None:
        raise ValueError("this chat was listed without its messages")
    return chat.messages


class Caller(Protocol):
    username: str
    email: str
    uid: str


class ChatService:
    def __init__(self, stronghold: StrongholdForwarder, who: Caller) -> None:
        self._stronghold = stronghold
        self._who = who

    async def _call(self, method: str, path: str, body: Any = None) -> Any:
        answer = await self._stronghold.forward(method, path, self._who, json=body)  # type: ignore[arg-type]
        if answer.status < 300:
            return json.loads(answer.body) if answer.body else None
        try:
            detail = json.loads(answer.body).get("detail")
        except (ValueError, AttributeError):
            detail = None
        if answer.status == 404:
            raise (FolderNotFound(path) if detail == "Folder not found" else ChatNotFound(path))
        if answer.status == 413:
            raise ChatLimitError(str(detail))
        if answer.status == 422 and path.endswith("/branch"):
            raise NotABranchPoint(path)
        raise HTTPException(answer.status, detail if isinstance(detail, str) else "Stronghold refused the request")

    async def list(self) -> list[ChatRecord]:
        """Newest first, without transcripts."""
        return [ChatRecord.of(doc) for doc in await self._call("GET", "/chats")]

    async def get(self, chat_id: str) -> ChatRecord:
        return ChatRecord.of(await self._call("GET", f"/chats/{chat_id}"))

    async def put(self, chat_id: str, title: str, agent_id: str | None, messages: list[ChatMessage]) -> ChatRecord:
        """Creates the chat or replaces its title, agent and transcript."""
        return ChatRecord.of(await self._call(
            "PUT", f"/chats/{chat_id}", {"title": title, "agent_id": agent_id, "messages": messages}))

    async def branch(self, source_id: str, upto: int) -> ChatRecord:
        """A new chat holding the source's messages up to and including answer `upto`."""
        return ChatRecord.of(await self._call("POST", f"/chats/{source_id}/branch", {"upto": upto}))

    async def replace_messages(self, chat_id: str, messages: list[ChatMessage], agent_id: str | None = None) -> ChatRecord:
        """New transcript for an existing chat, keeping its title (and its agent unless one is given)."""
        return ChatRecord.of(await self._call(
            "PUT", f"/chats/{chat_id}/messages", {"messages": messages, **({"agent_id": agent_id} if agent_id else {})}))

    async def update(
        self, chat_id: str, *, title: str | None = None, folder_id: int | None = UNSET,
        pinned: bool | None = None,
    ) -> ChatRecord:
        """Changes the supplied title, folder or pin. `folder_id` None
        takes the chat out of its folder; a folder of another account is FolderNotFound."""
        changes: dict[str, Any] = {"title": title, "pinned": pinned}
        body = {k: v for k, v in changes.items() if v is not None}
        if folder_id is not UNSET:
            body["folder_id"] = folder_id
        return ChatRecord.of(await self._call("PATCH", f"/chats/{chat_id}", body))

    async def delete(self, chat_id: str) -> None:
        """Deletes the chat and its share links."""
        await self._call("DELETE", f"/chats/{chat_id}")

    async def delete_all(self) -> None:
        await self._call("DELETE", "/chats")
