"""Environment configuration with native-development defaults."""

import os
from pathlib import Path

from .keyring import Keyring


def from_env(service: str | None = None, data_dir: Path | str = ".data") -> Keyring:
    return Keyring(os.environ.get("CITADEL_SERVICE", service or ""),
        os.environ.get("CITADEL_TRUST_DIR", str(Path.home() / ".citadel" / "trust")),
        os.environ.get("CITADEL_IDENTITY_DIR", str(Path(data_dir) / "identity")))
