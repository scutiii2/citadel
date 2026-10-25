"""Load mcp_server's single ``.env`` into the process environment.
A missing ``.env`` is built from legacy ``.secrets/*.env`` files, else ``.env.example``; must run before any ``src.*`` import that reads settings."""

from __future__ import annotations

import shutil
from pathlib import Path

from dotenv import load_dotenv


def migrate_legacy_secrets(env_path: Path, legacy_dir: Path) -> bool:
    """Build ``env_path`` from ``legacy_dir/*.env``; True if written.
    No-op when ``env_path`` exists or no legacy file does; each file is copied verbatim under a source header."""
    if env_path.exists() or not legacy_dir.is_dir():
        return False
    legacy_files = sorted(legacy_dir.glob("*.env"))
    if not legacy_files:
        return False
    parts = []
    for legacy in legacy_files:
        body = legacy.read_text(encoding="utf-8")
        parts.append(f"# ---- from {legacy_dir.name}/{legacy.name} ----\n{body.rstrip()}\n")
    env_path.write_text("\n".join(parts), encoding="utf-8")
    return True


def ensure_env_file(env_path: Path, example_path: Path, legacy_dir: Path) -> None:
    """Make sure ``env_path`` exists: migrate legacy files, else copy the example."""
    if env_path.exists():
        return
    if migrate_legacy_secrets(env_path, legacy_dir):
        return
    if example_path.exists():
        shutil.copyfile(example_path, env_path)


def load_env_file(
    env_path: Path = Path(".env"),
    example_path: Path = Path(".env.example"),
    legacy_dir: Path = Path(".secrets"),
) -> None:
    """Ensure ``.env`` exists, then load it (existing environment wins)."""
    ensure_env_file(env_path, example_path, legacy_dir)
    load_dotenv(env_path)
