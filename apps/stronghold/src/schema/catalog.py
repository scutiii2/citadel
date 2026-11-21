"""Every Treasury collection Stronghold uses: who owns it, how it is keyed and how an account's data leaves.

This is the one list. A test fails when code touches a collection that is missing here, and
`GET /schema` shows it to the admin app (Plan 7).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.schema.models import ChatDoc, ChatFolderDoc, ChatMessagesDoc, Doc, ShareDoc, UsageRecordDoc

STATE = "schema_state"


@dataclass(frozen=True)
class Collection:
    name: str
    domain: str
    key: str  # how a document's key is built, for people
    model: type[Doc] | None = None  # None: not checked yet (a later plan can add one)
    purge: str | None = None  # the DELETE route that removes an account's documents; None: purged with its parent


CATALOG: tuple[Collection, ...] = (
    Collection("chats", "chats", "<owner uid>:<chat id>", ChatDoc, "/chats/accounts/{uid}"),
    Collection("chat_messages", "chats", "<owner uid>:<chat id>", ChatMessagesDoc, "/chats/accounts/{uid}"),
    Collection("chat_folders", "chats", "<owner uid>:<folder id>", ChatFolderDoc, "/chats/accounts/{uid}"),
    Collection("shared_chats", "shares", "sha256 of the link token", ShareDoc, "/shares/accounts/{uid}"),
    Collection("usage_records", "usage", "<owner uid>:<random>", UsageRecordDoc, "/usage/accounts/{uid}"),
    Collection("notes", "notes", "<note id>", None, "/notes/accounts/{uid}"),
    Collection("prompt_templates", "templates", "<owner uid>:<template id>", None, "/templates/accounts/{uid}"),
    Collection("account_agents", "agents", "<owner uid>", None, "/account-agents/accounts/{uid}"),
    Collection("user_extensions", "extensions", "<owner uid>:<slug>", None, "/user-extensions/accounts/{uid}"),
    Collection("tuning_limits", "tuning", "<owner uid>", None, "/tuning/accounts/{uid}"),
    Collection("ticket_seen", "tickets", "<owner uid>:<ticket id>", None, "/tickets/accounts/{uid}"),
    Collection("brain_connections", "brains", "instance | personal-<hash of uid>", None, "/brains/accounts/{uid}"),
    Collection("brain_connection_revisions", "brains", "<connection id>:<revision>", None, "/brains/accounts/{uid}"),
    Collection("brain_promotions", "brains", "<hash>", None, "/brains/accounts/{uid}"),
    Collection("brain_promotion_requests", "brains", "<hash>", None, "/brains/accounts/{uid}"),
    Collection("brain_promotion_attempts", "brains", "<promotion id>:<attempt>", None, "/brains/accounts/{uid}"),
    Collection("brain_promotion_decisions", "brains", "<promotion id>:<attempt>", None, "/brains/accounts/{uid}"),
    Collection("brain_suggestions", "brains", "<hash>", None, "/brains/accounts/{uid}"),
    Collection("brain_stacks", "brain", "<owner uid>:<chat id>", None, "/stack/accounts/{uid}"),
    Collection("brain_shares", "brain", "<share id>", None, "/brain/shares/accounts/{uid}"),
    Collection("brain_blocks", "brain", "<recipient uid>:<blocked uid>", None, "/brain/shares/accounts/{uid}"),
    Collection("brain_proposals", "brain", "<proposal id>"),
    Collection(STATE, "schema", "stronghold"),
)

BY_NAME = {c.name: c for c in CATALOG}
