"""Who a Stronghold MCP tool call is for: the signed requester plus a chat id the account owns."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from dataclasses import dataclass

from src.citadel_auth import AuthError, requester_context

_CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ScopeError(Exception):
    """The call cannot be tied to one account's chat; the tool answers with this message."""


@dataclass(frozen=True)
class Scope:
    uid: str
    chat_id: str


def _request_context():
    from mcp.server.lowlevel.server import request_ctx

    try:
        return request_ctx.get()
    except LookupError:
        return None


@asynccontextmanager
async def resolve_scope(app):
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
    chat_id = extras.get("chat_id")
    if not isinstance(chat_id, str) or not _CHAT_ID.fullmatch(chat_id):
        raise ScopeError("This call is not tied to a chat.")
    try:
        async with requester_context(app.state.keyring, caller, token, "stronghold") as who:
            if who is None:
                raise ScopeError("No signed requester.")
            if not await app.state.chats.exists(who.uid, chat_id):
                raise ScopeError("This chat does not belong to the asking account.")
            yield Scope(who.uid, chat_id)
    except AuthError:
        raise ScopeError("The requester could not be verified.") from None
