"""Primes a valid agent file and pinned-provider config before any test
module imports src.agents.agent_config / src.server - agent_spec.current()
needs AI_AGENT_FILE, and both modules resolve PROVIDER_ID/MODEL once at
import time (see agent_config.py's module docstring) and raise
AgentConfigError immediately if AI_AGENT_PROVIDER or its API key isn't
set, which would otherwise break collection of test_server.py.

Set directly on os.environ (not via a monkeypatch fixture, which only
applies inside a running test) since this must be in place before pytest
even imports the test modules. test_agent_config.py's own tests still
freely override/clear these per test via monkeypatch - that only affects
the duration of each test, never this module-level default.
"""

import json
import os
import tempfile
from pathlib import Path

# An anthropic entry specialist (it keeps the generic tool loop; orchestrators always plan) on port 9100, id "claude-agent".
_AGENT_FILE = Path(tempfile.mkdtemp(prefix="ai_agent_spec_")) / "claude-agent.json"
_AGENT_FILE.write_text(
    json.dumps({"port": 9100, "entry": True, "llm": {"provider": "anthropic"}, "role": "specialist"}),
    encoding="utf-8",
)
os.environ.setdefault("AI_AGENT_FILE", str(_AGENT_FILE))
os.environ.setdefault("AI_AGENT_PROVIDER", "anthropic")
os.environ.setdefault("CLAUDE_API_KEY", "test-key")


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def auth_stack(tmp_path_factory):
    import asyncio
    from src.citadel_auth.testing import make_stack
    return asyncio.run(make_stack(tmp_path_factory.mktemp("service-auth")))


@pytest.fixture(autouse=True)
def service_identity(auth_stack, monkeypatch):
    from src.runtime import internal_auth
    monkeypatch.setattr(internal_auth, "keyring", auth_stack["legion"])
    internal_auth._latest.clear()
    yield
    internal_auth._latest.clear()


@pytest.fixture(autouse=True)
def _default_classifier_settings(monkeypatch):
    """Tests see the classifier defaults (everything off), never the developer's own `classifier`
    section in configs/config_tuning.json. Tests that need a section patch read_section themselves."""
    from src.providers.decision import settings

    settings.reset_cache()
    monkeypatch.setattr(settings, "read_section", lambda path, name, default=None: {})
    yield
    settings.reset_cache()


@pytest.fixture(autouse=True)
def _isolated_tuning_overrides(monkeypatch, tmp_path):
    """The admin's tuning edits (tool-call limits included) come from an empty per-test database, never the developer's settings.db."""
    from src.runtime import tool_batch_settings, tuning_overrides

    from src.gateway import sealing
    from src.providers import cooldown
    from src.runtime import counters

    monkeypatch.setattr(counters, "DB", tmp_path / "stats.db")
    monkeypatch.setattr(sealing, "KEY_FILE", tmp_path / "secret.key")
    monkeypatch.delenv("LEGION_SECRET_KEY", raising=False)
    sealing.reset()
    monkeypatch.setattr(cooldown, "DB", tmp_path / "cooldowns.db")
    monkeypatch.setattr(cooldown, "_synced_at", float("-inf"))
    monkeypatch.setattr(tuning_overrides, "PATH", tmp_path / "tuning.db")
    monkeypatch.setattr(tuning_overrides, "_migrated", set())
    monkeypatch.setattr(tool_batch_settings, "_cache", None)


@pytest.fixture(autouse=True)
def _no_confidential_check(monkeypatch):
    """Tests do not call the Jev checker (and its fail-closed answer): every request counts as public unless a test
    patches is_confidential itself. tests/test_confidentiality.py keeps a reference to the real function."""
    from unittest.mock import AsyncMock

    from src.runtime import confidentiality

    monkeypatch.setattr(confidentiality, "is_confidential", AsyncMock(return_value=False))


@pytest.fixture(autouse=True)
def _fresh_tuning_caches():
    """The readers of config_tuning.json cache what they parsed. A test that points one at its own file must not leave
    that behind for the next test, whatever order the files run in."""
    from src.providers import gateway_failover, token_limits
    from src.providers.decision import settings

    for reset in (token_limits.reset_cache, gateway_failover.reset_cache, settings.reset_cache):
        reset()
    yield
    for reset in (token_limits.reset_cache, gateway_failover.reset_cache, settings.reset_cache):
        reset()


@pytest.fixture(autouse=True)
def _isolated_gateway_database(monkeypatch, tmp_path):
    """Gateway entries come from an empty per-test database, never the developer's real settings.db."""
    from src import gateway

    monkeypatch.setattr(gateway, "_database", lambda: tmp_path / "gateways.db")
    for name in ("_chat", "_chat_store", "_decision", "_decision_store"):
        monkeypatch.setattr(gateway, name, None)


@pytest.fixture(autouse=True)
def _isolated_agent_registry(monkeypatch, tmp_path):
    """Point the agent registry at empty, per-test files so no test reads or
    rewrites the developer's real agent registry (roster_for and
    delegation.call reload it). Tests needing agents set their own."""
    from src.agents import agent_registry

    monkeypatch.setattr(agent_registry, "_CONFIG_PATH", tmp_path / "registry" / "agent_registry.json")
    monkeypatch.setattr(agent_registry, "_AGENTS", [])
    monkeypatch.setattr(agent_registry, "_AGENTS_BY_ID", {})


import tempfile  # noqa: E402

# server.ask() appends every turn to the usage log; keep test turns out of
# the real ai_agent/.data/usage/.
os.environ.setdefault("AI_AGENT_USAGE_DIR", tempfile.mkdtemp(prefix="ai_agent_usage_"))


@pytest.fixture(autouse=True)
def _saved_gateways(monkeypatch):
    """Every gateway counts as saved in ConversationGateway; tests never call the service."""
    from src.providers import gateway_client

    monkeypatch.setattr(gateway_client, "is_saved", lambda gateway: True)


@pytest.fixture(autouse=True)
def _no_decision_gateway_listing(monkeypatch):
    """DecisionGateway cannot be asked which gateways it has; tests never call the service."""
    from src.providers.decision import gateway_client

    monkeypatch.setattr(gateway_client, "saved_gateways", lambda: {"laya": True, "jev": True})
