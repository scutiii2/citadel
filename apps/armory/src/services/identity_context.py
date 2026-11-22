"""Account identity comes only from verified Portcullis requester tokens."""

from __future__ import annotations

from contextvars import ContextVar
from src.citadel_auth import current_requester


_username: ContextVar[str] = ContextVar("requester_username", default="")
_email: ContextVar[str] = ContextVar("requester_email", default="")
_uid: ContextVar[str] = ContextVar("requester_uid", default="")




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
