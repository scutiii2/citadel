"""Account identity comes only from verified Portcullis requester tokens."""

from __future__ import annotations

from contextvars import ContextVar
from src.citadel_auth import current_requester


_username: ContextVar[str] = ContextVar("requester_username", default="")
_email: ContextVar[str] = ContextVar("requester_email", default="")
_uid: ContextVar[str] = ContextVar("requester_uid", default="")




def _from_request_meta(field: str) -> str:
    """Read only non-identity narrowing hints from unsigned MCP metadata."""
    if field != "brain_scope":
        return ""
    from mcp.server.lowlevel.server import request_ctx

    try:
        meta = request_ctx.get().meta
    except LookupError:
        return ""
    value = (meta.model_extra or {}).get(field) if meta is not None else None
    return value if isinstance(value, str) else ""


def current_username() -> str:
    requester = current_requester()
    return requester.username if requester else _username.get()


def current_email() -> str:
    requester = current_requester()
    return requester.email if requester else _email.get()


def current_uid() -> str:
    """The account's stable id (never changes, never reused), unlike the username."""
    requester = current_requester()
    return requester.uid if requester else _uid.get()


class IdentityContextMiddleware:
    """Identity binding belongs to service auth and per-tool MCP verification."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)
