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

# An anthropic orchestrator on port 9100, id "claude-agent".
_AGENT_FILE = Path(tempfile.mkdtemp(prefix="ai_agent_spec_")) / "claude-agent.json"
_AGENT_FILE.write_text(
    json.dumps({"port": 9100, "entry": True, "llm": {"provider": "anthropic"}, "role": "orchestrator"}),
    encoding="utf-8",
)
os.environ.setdefault("AI_AGENT_FILE", str(_AGENT_FILE))
os.environ.setdefault("AI_AGENT_PROVIDER", "anthropic")
os.environ.setdefault("CLAUDE_API_KEY", "test-key")


import pytest  # noqa: E402


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
