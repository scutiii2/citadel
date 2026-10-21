from dataclasses import replace

import pytest

from src.services import brain_resolver, identity_context
from src.capabilities.obsidian.utils.gateway import ObsidianGateway, ObsidianGatewayError


def test_missing_identity_and_token_fail_closed(monkeypatch):
    monkeypatch.setattr(brain_resolver, "settings", replace(brain_resolver.settings, internal_api_token=""))
    with pytest.raises(ObsidianGatewayError, match="authentication"):
        brain_resolver.resolve("instance", "read", "alice")


def test_auto_save_metadata_refuses_another_destination_before_remote_request(monkeypatch):
    monkeypatch.setattr(brain_resolver, "settings", replace(brain_resolver.settings, internal_api_token="test-token"))
    monkeypatch.setattr(identity_context, "_from_request_meta", lambda key: "personal" if key == "brain_scope" else "")
    with pytest.raises(ObsidianGatewayError, match="destination"):
        brain_resolver.resolve("instance", "write", "alice")


@pytest.mark.parametrize("version,allowed", [("5.2.0", True), ("5.1.9", False), ("unknown", False), ("5.2.0-beta", False)])
def test_promotion_requires_known_conditional_create_support(monkeypatch, version, allowed):
    gateway = ObsidianGateway("https://vault.invalid", "test-key")
    monkeypatch.setattr(gateway, "_json", lambda *args: {"versions": {"self": version}})
    if allowed:
        gateway.require_create_only()
    else:
        with pytest.raises(ObsidianGatewayError, match="conditional create"):
            gateway.require_create_only()
