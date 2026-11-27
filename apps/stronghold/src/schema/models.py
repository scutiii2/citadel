"""Shapes of the documents Stronghold stores for chats, shares and usage.

Treasury keeps any JSON, so these models are the schema: a store builds its document, checks it here and
only then writes it. A document that does not fit raises `pydantic.ValidationError`, so a bug shows up at
the write, not as a broken page later. Fields the stores add over time are allowed (`extra="allow"`),
because older documents must keep reading; fields named here are the ones code relies on.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Doc(BaseModel):
    """Every document repeats its own key and owner: purge and listing filter on `owner`."""

    model_config = ConfigDict(extra="allow")

    key: str = Field(min_length=1)
    owner: str = Field(min_length=1)


class ChatDoc(Doc):
    """`chats`: details only. The transcript is in `chat_messages` so a list never reads one."""

    chat_id: str = Field(min_length=1)
    title: str = Field(max_length=120)
    agent_id: str | None = None
    folder_id: int | None = None
    pinned: bool = False
    message_count: int = Field(default=0, ge=0)
    created_at: str
    updated_at: str


class ChatMessagesDoc(Doc):
    """`chat_messages`: one transcript, under the same key as its chat."""

    chat_id: str = Field(min_length=1)
    messages: list[dict[str, Any]]


class ChatFolderDoc(Doc):
    id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=60)
    position: int = Field(ge=0)
    created_at: str


class ChatFileHoldDoc(Doc):
    """`chat_file_holds`: a call to Armory still to be sent."""

    chat_id: str | None
    op: Literal["hold", "release", "release_all"]
    file_ids: list[str]
    version: str = Field(min_length=1)


class ShareDoc(Doc):
    """`shared_chats`: keyed by the SHA-256 of the link's token, which is never stored."""

    id: int = Field(ge=1)
    chat_id: str = Field(min_length=1)
    title: str
    messages: list[dict[str, Any]]
    message_count: int = Field(ge=0)
    created_at: str
    expires_at: str | None = None


class UsageRecordDoc(Doc):
    """`usage_records`: one row per agent call. `id` stays below 2^53 so a browser reads it exactly."""

    id: int = Field(ge=0, lt=2**53)
    turn_id: str
    kind: str = Field(min_length=1)
    chat_id: str | None = None
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    created_at: str
    total_tokens: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)


class UsageAllowanceDoc(Doc):
    """`usage_allowances`: one account's free resets, limit boosts, cleared times and automatic-use switch."""

    resets: list[dict[str, Any]]
    boosts: list[dict[str, Any]]
    cleared: dict[str, str | None]
    auto_use: bool


def checked(model: type[Doc], doc: dict[str, Any]) -> dict[str, Any]:
    """`doc` itself when it fits `model`; raises ValidationError otherwise. Written documents are never reshaped."""
    model.model_validate(doc)
    return doc
