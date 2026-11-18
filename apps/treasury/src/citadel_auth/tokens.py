"""Strict compact Ed25519 JWT service assertions."""

import time
import uuid
from dataclasses import dataclass

import jwt

from .errors import AuthError
from .keyring import Keyring

LEEWAY = 30


@dataclass(frozen=True)
class Caller:
    name: str


def encode(keyring: Keyring, claims: dict) -> str:
    if keyring.private_key is None:
        raise AuthError("identity not initialized")
    return jwt.encode(claims, keyring.private_key, algorithm="EdDSA", headers={"kid": keyring.kid})


def sign_assertion(keyring: Keyring, aud: str) -> str:
    now = int(time.time())
    return encode(keyring, {"iss": keyring.service, "aud": aud, "iat": now,
                            "exp": now + 60, "jti": uuid.uuid4().hex})


async def decode(keyring: Keyring, token: str, aud: str, *, requester: bool = False) -> dict:
    try:
        if not isinstance(token, str) or len(token) > 16384:
            raise AuthError("invalid token")
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
        issuer = unverified.get("iss")
        if not isinstance(issuer, str):
            raise AuthError("invalid claims")
        if requester and issuer != "portcullis":
            raise AuthError("requester issuer must be portcullis")
        if header.get("alg") != "EdDSA" or not isinstance(header.get("kid"), str):
            raise AuthError("invalid signature algorithm or key id")
        key = await keyring.public_key(issuer, header["kid"])
        claims = jwt.decode(token, key, algorithms=["EdDSA"], audience=aud, issuer=issuer,
            leeway=LEEWAY, options={"require": ["iss", "aud", "iat", "exp", "jti"]})
        if any(type(claims[name]) is not int for name in ("iat", "exp")):
            raise AuthError("invalid time claims")
        lifetime = 900 if requester else 60
        if claims["exp"] - claims["iat"] != lifetime:
            raise AuthError("invalid token lifetime")
        if not isinstance(claims["jti"], str) or not claims["jti"]:
            raise AuthError("invalid claims")
        if requester != (claims.get("typ") == "requester"):
            raise AuthError("wrong token type")
        return claims
    except jwt.ExpiredSignatureError as error:
        raise AuthError("expired token") from error
    except jwt.ImmatureSignatureError as error:
        raise AuthError("clock skew exceeds 30 seconds") from error
    except jwt.InvalidAudienceError as error:
        raise AuthError("wrong audience") from error
    except jwt.InvalidSignatureError as error:
        raise AuthError("invalid signature") from error
    except (jwt.PyJWTError, TypeError, KeyError) as error:
        raise AuthError("invalid token claims or signature") from error


async def verify_assertion(keyring: Keyring, token: str, aud: str) -> Caller:
    claims = await decode(keyring, token, aud)
    keyring.remember(claims["iss"], claims["jti"], claims["exp"] + LEEWAY)
    return Caller(claims["iss"])
