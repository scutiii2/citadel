"""Portcullis alone asserts user identity; downstream services only forward it."""

import time
import uuid
from contextvars import ContextVar
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


def current_requester() -> Requester | None:
    return _requester.get()


def current_requester_token() -> str:
    return _requester_token.get()


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
