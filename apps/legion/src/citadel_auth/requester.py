"""Portcullis alone asserts user identity; downstream services only forward it."""

import time
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

from .errors import AuthError
from .keyring import Keyring
from .tokens import decode, encode


@dataclass(frozen=True)
class Requester:
    uid: str
    username: str
    email: str


_requester: ContextVar[Requester | None] = ContextVar("citadel_requester", default=None)
_requester_token: ContextVar[str] = ContextVar("citadel_requester_token", default="")
_token_provider: ContextVar[object] = ContextVar("citadel_requester_token_provider", default=None)


def current_requester() -> Requester | None:
    return _requester.get()


def current_requester_token() -> str:
    provider = _token_provider.get()
    return provider() if provider is not None else _requester_token.get()


@contextmanager
def requester_token_provider(provider):
    """Let a running job forward its latest verified credential across child tasks."""
    handle = _token_provider.set(provider)
    try:
        yield
    finally:
        _token_provider.reset(handle)


def mint_requester(keyring: Keyring, uid: str, username: str, email: str, aud: list[str]) -> str:
    if keyring.service != "portcullis":
        raise AuthError("only portcullis may mint requester tokens")
    if not isinstance(uid, str) or not uid:
        raise AuthError("invalid requester uid")
    now = int(time.time())
    return encode(keyring, {"typ": "requester", "iss": "portcullis", "sub": uid,
        "username": username, "email": email, "aud": aud, "iat": now, "exp": now + 900,
        "jti": uuid.uuid4().hex})


async def verify_requester(keyring: Keyring, token: str, aud: str) -> Requester:
    claims = await decode(keyring, token, aud, requester=True)
    if any(not isinstance(claims.get(name), str) for name in ("sub", "username", "email")) or not claims["sub"]:
        raise AuthError("invalid requester claims")
    return Requester(claims["sub"], claims["username"], claims["email"])


@asynccontextmanager
async def requester_context(keyring: Keyring, caller, token: str, aud: str):
    """Bind one MCP tool call, clearing any identity inherited from session startup."""
    from .asgi import _caller
    from .errors import Forbidden
    from .policy import may_forward
    requester = None
    if token:
        if caller is None or not may_forward(aud, caller.name):
            raise Forbidden("caller not allowed to forward requester")
        requester = await verify_requester(keyring, token, aud)
    caller_handle = _caller.set(caller)
    requester_handle = _requester.set(requester)
    token_handle = _requester_token.set(token)
    try:
        yield requester
    finally:
        _requester_token.reset(token_handle)
        _requester.reset(requester_handle)
        _caller.reset(caller_handle)
