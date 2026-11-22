"""Who a Stronghold MCP tool call is for: the signed requester, plus (for short-term memory) a chat id the account owns."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from dataclasses import dataclass

from src.citadel_auth import AuthError, requester_context

_CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
OUTSIDE_PREFIX = "oc_"


def is_outside(uid: str) -> bool:
    """True for the synthetic UID Portcullis assigns to an outside client."""
    return uid.startswith(OUTSIDE_PREFIX)


class ScopeError(Exception):
    """The call cannot be tied to one account (and chat); the tool answers with this message."""


@dataclass(frozen=True)
class Scope:
    uid: str
    chat_id: str


@dataclass(frozen=True)
class Account:
    uid: str
    username: str = ""
    email: str = ""


def _request_context():
    from mcp.server.lowlevel.server import request_ctx

    try:
        return request_ctx.get()
    except LookupError:
        return None


def _credentials():
    """Read the signed requester token and metadata from Legion's call."""
    context = _request_context()
    if context is None:
        raise ScopeError("No request context.")
    caller, _, header_token = getattr(context.request, "scope", {}).get("citadel_auth", (None, None, ""))
    if caller is None or caller.name != "legion":
        raise ScopeError("Only Legion may use this server.")
    extras = (context.meta.model_extra or {}) if context.meta is not None else {}
    token = extras.get("requester_token", header_token)
    if not isinstance(token, str) or not token:
        raise ScopeError("No signed requester.")
    return caller, token, extras


@asynccontextmanager
async def _verified(app, caller, token):
    try:
        async with requester_context(app.state.keyring, caller, token, "stronghold") as who:
            if who is None:
                raise ScopeError("No signed requester.")
            yield who
    except AuthError:
        raise ScopeError("The requester could not be verified.") from None


@asynccontextmanager
async def resolve_scope(app):
    caller, token, extras = _credentials()
    chat_id = extras.get("chat_id")
    async with _verified(app, caller, token) as who:
        if is_outside(who.uid):
            raise ScopeError("Not available to outside clients.")
        if not isinstance(chat_id, str) or not _CHAT_ID.fullmatch(chat_id):
            raise ScopeError("This call is not tied to a chat.")
        if not await app.state.chats.exists(who.uid, chat_id):
            raise ScopeError("This chat does not belong to the asking account.")
        yield Scope(who.uid, chat_id)


@asynccontextmanager
async def resolve_account(app, *, outside_ok: bool = False):
    """For account-wide tools (long-term memory): the verified account, no chat id needed."""
    caller, token, _extras = _credentials()
    async with _verified(app, caller, token) as who:
        if is_outside(who.uid) and not outside_ok:
            raise ScopeError("Not available to outside clients.")
        yield Account(who.uid, getattr(who, "username", "") or who.uid, getattr(who, "email", "") or "")
