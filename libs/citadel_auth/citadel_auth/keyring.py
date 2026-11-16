"""Private service identity and receiver-local public-key/replay caches."""

import asyncio
import hashlib
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .errors import AuthError
from .policy import SERVICES


def key_id(public: Ed25519PublicKey) -> str:
    raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


class Keyring:
    """Load files off the event loop; never publish a private key into trust."""

    def __init__(self, service: str, trust_dir: Path | str, identity_dir: Path | str):
        if service not in SERVICES:
            raise AuthError("unknown caller")
        self.service = service
        self.trust_dir = Path(trust_dir).expanduser()
        self.identity_dir = Path(identity_dir).expanduser()
        if self.identity_dir.resolve().is_relative_to(self.trust_dir.resolve()):
            raise AuthError("private identity must be outside trust directory")
        self.private_key: Ed25519PrivateKey | None = None
        self.kid = ""
        self._public: dict[str, tuple[str, Ed25519PublicKey]] = {}
        self._replays: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._replay_lock = threading.Lock()
        self._identity_lock = threading.Lock()

    async def ensure_identity(self) -> None:
        if self.private_key is None:
            await asyncio.to_thread(self._ensure_identity)

    def _ensure_identity(self) -> None:
        with self._identity_lock:
            if self.private_key is not None:
                return
            self.identity_dir.mkdir(parents=True, exist_ok=True)
            path = self.identity_dir / "key.pem"
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                private = serialization.load_pem_private_key(path.read_bytes(), password=None)
            else:
                private = Ed25519PrivateKey.generate()
                with os.fdopen(descriptor, "wb") as output:
                    output.write(private.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            if not isinstance(private, Ed25519PrivateKey):
                raise AuthError("identity is not Ed25519")
            if os.name != "nt":
                path.chmod(0o600)
            public = private.public_key()
            folder = self.trust_dir / self.service
            folder.mkdir(parents=True, exist_ok=True)
            public_bytes = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            # Atomic publish: another service never observes a partially-written public key.
            temporary = folder / f"key.{os.getpid()}.{threading.get_ident()}.tmp"
            temporary.write_bytes(public_bytes)
            temporary.replace(folder / "key.pub")
            self.private_key = private
            self.kid = key_id(public)

    async def reload(self, service: str) -> Ed25519PublicKey:
        if service not in SERVICES:
            raise AuthError("unknown caller")
        try:
            raw = await asyncio.to_thread((self.trust_dir / service / "key.pub").read_bytes)
            public = serialization.load_pem_public_key(raw)
            if not isinstance(public, Ed25519PublicKey):
                raise ValueError("not Ed25519")
        except (OSError, ValueError) as error:
            self._public.pop(service, None)
            raise AuthError("unreadable trust key") from error
        self._public[service] = (key_id(public), public)
        return public

    async def public_key(self, service: str, kid: str | None = None) -> Ed25519PublicKey:
        if service not in SERVICES:
            raise AuthError("unknown caller")
        cached = self._public.get(service)
        if cached is None or (kid is not None and cached[0] != kid):
            await self.reload(service)
            cached = self._public[service]
        if kid is not None and cached[0] != kid:
            raise AuthError("unknown key id")
        return cached[1]

    def remember(self, issuer: str, jti: str, expiry: float) -> None:
        """Reject replay atomically; bound receiver memory to 50,000 assertions."""
        now = time.time()
        with self._replay_lock:
            while self._replays and next(iter(self._replays.values())) <= now:
                self._replays.popitem(last=False)
            key = (issuer, jti)
            if self._replays.get(key, 0) > now:
                raise AuthError("replayed assertion")
            self._replays[key] = expiry
            while len(self._replays) > 50_000:
                self._replays.popitem(last=False)
