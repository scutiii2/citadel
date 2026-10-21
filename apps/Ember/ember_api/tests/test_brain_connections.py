import asyncio

import pytest
from cryptography.fernet import Fernet

from src.services.brain_connections import BrainConnections, BrainError, ConnectionInput
from src.services.secret_box import SecretBox
from tests.conftest import FakeDbGateway


def run(coro):
    return asyncio.run(coro)


def test_encrypted_settings_key_preservation_and_revisions():
    store = FakeDbGateway()
    service = BrainConnections(store, SecretBox(Fernet.generate_key().decode()))
    first = run(service.save("personal", "alice", ConnectionInput(
        label="Mine", endpoint="https://vault.lan:27124", api_key="private-vault-token", expected_revision=0)))
    assert first["revision"] == 1 and first["credential_configured"]
    assert "private-vault-token" not in repr(first)
    assert "private-vault-token" not in repr(store.records)
    second = run(service.save("personal", "alice", ConnectionInput(
        label="Renamed", endpoint="https://vault.lan:27124", expected_revision=1)))
    assert second["generation"] != first["generation"]
    snapshot = run(service.resolve("personal", "alice", write=False, publish=False))
    assert snapshot["api_key"] == "private-vault-token"
    assert snapshot["revision"] == 2
    with pytest.raises(BrainError, match="changed"):
        run(service.save("personal", "alice", ConnectionInput(
            label="Stale", endpoint="https://vault.lan:27124", expected_revision=1)))


def test_personal_isolation_disable_and_instance_publish_permission():
    service = BrainConnections(FakeDbGateway(), SecretBox(Fernet.generate_key().decode()))
    run(service.save("personal", "alice", ConnectionInput(
        label="Mine", endpoint="https://vault.lan", api_key="key", allow_write=True)))
    with pytest.raises(BrainError):
        run(service.resolve("personal", "bob", write=False, publish=False))
    run(service.save("instance", "", ConnectionInput(
        label="Shared", endpoint="https://127.0.0.1:27124", api_key="shared", allow_write=True)))
    with pytest.raises(BrainError, match="publish"):
        run(service.resolve("instance", "alice", write=True, publish=False))
    assert run(service.resolve("instance", "alice", write=True, publish=True))["scope"] == "instance"
    run(service.save("personal", "alice", ConnectionInput(
        label="Mine", endpoint="https://vault.lan", enabled=False, expected_revision=1)))
    with pytest.raises(BrainError, match="disabled"):
        run(service.resolve("personal", "alice", write=False, publish=False))


@pytest.mark.parametrize("endpoint", ["http://vault.lan", "https://u:p@vault.lan", "https://vault.lan/?key=x", "https://vault.lan/#secret"])
def test_rejects_invalid_endpoints(endpoint):
    with pytest.raises(ValueError):
        ConnectionInput(label="Mine", endpoint=endpoint)
