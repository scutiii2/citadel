"""Seal the one-time Stronghold snapshot to a signed Armory migration challenge."""

import base64
import hashlib
import json
import time
import uuid

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import AuthError
from .tokens import LEEWAY, decode, encode

_PURPOSE = "instance-brain-migration/v1"


def _sign(keyring, audience, **claims):
    now = int(time.time())
    return encode(keyring, {"iss": keyring.service, "aud": audience, "iat": now,
                            "exp": now + 60, "jti": uuid.uuid4().hex, "purpose": _PURPOSE, **claims})


async def _verify(keyring, token, issuer, action):
    claims = await decode(keyring, token, keyring.service)
    if (claims["iss"], claims.get("purpose"), claims.get("action")) != (issuer, _PURPOSE, action):
        raise AuthError("invalid migration assertion")
    keyring.remember(issuer, claims["jti"], claims["exp"] + LEEWAY)
    return claims


def _public(private):
    return private.public_key().public_bytes_raw().hex()


def _box(private, peer, challenge):
    shared = private.exchange(X25519PublicKey.from_public_bytes(bytes.fromhex(peer)))
    derived = HKDF(algorithm=SHA256(), length=32, salt=hashlib.sha256(challenge.encode()).digest(),
                   info=_PURPOSE.encode()).derive(shared)
    return Fernet(base64.urlsafe_b64encode(derived))


def challenge(keyring):
    private = X25519PrivateKey.generate()
    return private, _sign(keyring, "stronghold", action="export", public=_public(private))


async def seal(keyring, token, load):
    claims = await _verify(keyring, token, "armory", "export")
    private = X25519PrivateKey.generate()
    box = _box(private, claims.get("public", ""), token)
    ciphertext = box.encrypt(json.dumps(await load()).encode()).decode()
    signature = _sign(keyring, "armory", action="snapshot", public=_public(private),
                      challenge=hashlib.sha256(token.encode()).hexdigest(),
                      digest=hashlib.sha256(ciphertext.encode()).hexdigest())
    return {"ciphertext": ciphertext, "signature": signature}


async def unseal(keyring, private, token, envelope):
    claims = await _verify(keyring, envelope["signature"], "stronghold", "snapshot")
    ciphertext = envelope["ciphertext"].encode()
    if (claims.get("challenge") != hashlib.sha256(token.encode()).hexdigest()
            or claims.get("digest") != hashlib.sha256(ciphertext).hexdigest()):
        raise AuthError("invalid migration snapshot")
    return json.loads(_box(private, claims["public"], token).decrypt(ciphertext))


def acknowledgement(keyring, revision, generation):
    return _sign(keyring, "stronghold", action="retire", revision=revision, generation=generation)


async def verify_acknowledgement(keyring, token):
    claims = await _verify(keyring, token, "armory", "retire")
    return claims["revision"], claims["generation"]
