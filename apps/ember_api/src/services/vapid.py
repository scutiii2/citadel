"""The VAPID key pair that identifies ember to browsers' push services, kept in `.env`.

Losing it only means every browser must subscribe to push again; nothing else depends on it.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid

from src.utils.config_loader import load_env_secrets

PRIVATE_NAME = "EMBER_VAPID_PRIVATE_KEY"
PUBLIC_NAME = "EMBER_VAPID_PUBLIC_KEY"


@dataclass(frozen=True)
class VapidKeys:
    private: str
    public: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _set(env_path: Path, name: str, value: str) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    line = re.compile(rf"(?m)^{name}=.*$")
    if line.search(text):
        text = line.sub(lambda _m: f"{name}={value}", text, count=1)
    else:
        text = f"{text}{'' if not text or text.endswith(chr(10)) else chr(10)}{name}={value}\n"
    env_path.write_text(text, encoding="utf-8")


def ensure_vapid_keys(env_path: Path) -> VapidKeys:
    env = load_env_secrets(env_path)
    private, public = env.get(PRIVATE_NAME, "").strip(), env.get(PUBLIC_NAME, "").strip()
    if private and public:
        return VapidKeys(private, public)
    vapid = Vapid()
    vapid.generate_keys()
    private = _b64(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
    public = _b64(vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    _set(env_path, PRIVATE_NAME, private)
    _set(env_path, PUBLIC_NAME, public)
    return VapidKeys(private, public)
