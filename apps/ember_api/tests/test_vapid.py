from __future__ import annotations

from pathlib import Path

from py_vapid import Vapid

from src.services.vapid import ensure_vapid_keys


def test_keys_are_generated_once_and_persisted(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("OTHER=1", encoding="utf-8")
    first = ensure_vapid_keys(env)
    text = env.read_text(encoding="utf-8")
    assert "OTHER=1\n" in text and f"EMBER_VAPID_PRIVATE_KEY={first.private}" in text
    assert ensure_vapid_keys(env) == first
    Vapid.from_raw(first.private.encode())  # the private half is loadable by pywebpush


def test_a_half_written_pair_is_replaced(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EMBER_VAPID_PRIVATE_KEY=\nEMBER_VAPID_PUBLIC_KEY=old\n", encoding="utf-8")
    keys = ensure_vapid_keys(env)
    text = env.read_text(encoding="utf-8")
    assert text.count("EMBER_VAPID_PRIVATE_KEY=") == 1 and "old" not in text and keys.public in text
