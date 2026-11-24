"""Gateway secrets are encrypted in settings.db."""

import pytest

from src.citadel_auth import settings_store
from src.gateway import sealing
from src.gateway.conversation.store import GatewayStore as ChatStore
from src.gateway.decision.store import GatewayStore as DecisionStore


def _raw(path, table):
    return settings_store.read_all(path, table)


def test_a_saved_key_is_encrypted_on_disk_and_read_back_in_clear(tmp_path):
    store = ChatStore(tmp_path / "s.db", "g")
    store.put("claude", {"provider": "anthropic", "api_key": "sk-secret", "model": "m"})
    stored = _raw(tmp_path / "s.db", "g")["claude"]["api_key"]
    assert stored.startswith("enc:v1:") and "sk-secret" not in stored
    assert store.all()["claude"]["api_key"] == "sk-secret"
    assert "sk-secret" not in str(store.public()) and store.public()[0]["has_api_key"] is True


def test_editing_without_the_key_keeps_it_and_does_not_seal_twice(tmp_path):
    store = ChatStore(tmp_path / "s.db", "g")
    store.put("claude", {"provider": "anthropic", "api_key": "sk-secret", "model": "a"})
    first = _raw(tmp_path / "s.db", "g")["claude"]["api_key"]
    store.put("claude", {"provider": "anthropic", "model": "b"})
    assert store.all()["claude"]["api_key"] == "sk-secret" and store.all()["claude"]["model"] == "b"
    assert not _raw(tmp_path / "s.db", "g")["claude"]["api_key"].removeprefix("enc:v1:").startswith("enc")
    assert sealing.unseal(first) == "sk-secret"


def test_plain_text_rows_from_before_are_sealed_once(tmp_path):
    settings_store.put(tmp_path / "s.db", "d", "jev", {"kind": "typesafe", "url": "https://x", "model": "m", "api_key": "sk-old"})
    settings_store.put(tmp_path / "s.db", "d", "viaenv", {"kind": "typesafe", "url": "https://x", "model": "m", "api_key": "env:JEV_KEY"})
    store = DecisionStore(tmp_path / "s.db", "d")
    assert store.seal_rows() == 1 and store.seal_rows() == 0
    rows = _raw(tmp_path / "s.db", "d")
    assert rows["jev"]["api_key"].startswith("enc:v1:") and rows["viaenv"]["api_key"] == "env:JEV_KEY"
    assert store.all()["jev"]["api_key"] == "sk-old"


def test_an_env_reference_is_resolved_and_never_sealed(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_KEY", "sk-env")
    store = ChatStore(tmp_path / "s.db", "g")
    store.put("claude", {"provider": "anthropic", "api_key": "env:CLAUDE_KEY", "model": "m"})
    assert _raw(tmp_path / "s.db", "g")["claude"]["api_key"] == "env:CLAUDE_KEY"
    assert store.all()["claude"]["api_key"] == "sk-env"


def test_a_changed_key_reads_as_no_key_instead_of_garbage(tmp_path, monkeypatch):
    store = ChatStore(tmp_path / "s.db", "g")
    store.put("claude", {"provider": "anthropic", "api_key": "sk-secret", "model": "m"})
    monkeypatch.setattr(sealing, "KEY_FILE", tmp_path / "other.key")
    sealing.reset()
    assert store.all()["claude"]["api_key"] == "" and store.public()[0]["has_api_key"] is False


def test_the_key_comes_from_the_environment_or_a_private_file(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("LEGION_SECRET_KEY", key)
    sealing.reset()
    sealed = sealing.seal("hello")
    monkeypatch.delenv("LEGION_SECRET_KEY")
    sealing.reset()
    assert sealing.unseal(sealed) == ""  # another key: the file one, made now
    assert (tmp_path / "secret.key").is_file()
    monkeypatch.setenv("LEGION_SECRET_KEY", key)
    sealing.reset()
    assert sealing.unseal(sealed) == "hello"
