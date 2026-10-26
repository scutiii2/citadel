"""Per-request caller identity for audit trails, read from HTTP headers rather than a tool parameter, which an LLM could set.
IdentityContextMiddleware sets contextvars read via current_username()/current_email()/current_uid(); ai_agent's shared session sends it in each call's `_meta` instead. Both are only as trustworthy as the caller (see internal_token.py)."""

from __future__ import annotations

from contextvars import ContextVar

REQUESTER_USERNAME_HEADER = "x-requester-username"
REQUESTER_EMAIL_HEADER = "x-requester-email"
REQUESTER_UID_HEADER = "x-requester-uid"

_username: ContextVar[str] = ContextVar("requester_username", default="")
_email: ContextVar[str] = ContextVar("requester_email", default="")
_uid: ContextVar[str] = ContextVar("requester_uid", default="")


REQUESTER_META_KEY = "requester"


def _from_request_meta(field: str) -> str:
    """`field` of the current MCP request's `_meta.requester`, or ""."""
    from mcp.server.lowlevel.server import request_ctx

    try:
        meta = request_ctx.get().meta
    except LookupError:
        return ""
    requester = (meta.model_extra or {}).get(REQUESTER_META_KEY) if meta is not None else None
    value = requester.get(field) if isinstance(requester, dict) else None
    return value if isinstance(value, str) else ""


def current_username() -> str:
    return _username.get() or _from_request_meta("username")


def current_email() -> str:
    return _email.get() or _from_request_meta("email")


def current_uid() -> str:
    """The account's stable id (never changes, never reused), unlike the username."""
    return _uid.get() or _from_request_meta("uid")


class IdentityContextMiddleware:
    """Plain ASGI middleware (not BaseHTTPMiddleware, which runs the app in a separate task).
    Reads the identity headers off the scope, sets the contextvars for this request and resets them on exit."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = dict(scope.get("headers") or [])
        username = raw_headers.get(REQUESTER_USERNAME_HEADER.encode("latin-1"), b"").decode("utf-8")
        email = raw_headers.get(REQUESTER_EMAIL_HEADER.encode("latin-1"), b"").decode("utf-8")

        uid = raw_headers.get(REQUESTER_UID_HEADER.encode("latin-1"), b"").decode("utf-8")

        username_token = _username.set(username)
        email_token = _email.set(email)
        uid_token = _uid.set(uid)
        try:
            await self.app(scope, receive, send)
        finally:
            _username.reset(username_token)
            _email.reset(email_token)
            _uid.reset(uid_token)
