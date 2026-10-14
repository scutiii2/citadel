"""agent_store.py: validated create/update/delete of agents; edits go to the untracked overrides file."""

from __future__ import annotations

import json

import pytest

from src.agents import agent_spec, agent_store
from src.agents.agent_store import AgentStoreError


def _cfg(port, **extra):
    return {"label": "X", "port": port, "llm": {"provider": "anthropic", "gateway": "claude"}, **extra}


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "ember.json").write_text(json.dumps(_cfg(9100, entry=True)), encoding="utf-8")
    return tmp_path


def _overrides(folder):
    return json.loads((folder / ".overrides" / "agent_overrides.json").read_text())


def test_create_writes_an_override_and_lists_it(folder):
    agent_store.create_agent("calc", _cfg(9103), folder)
    assert _overrides(folder)["calc"]["port"] == 9103
    assert not (folder / "calc.json").exists()
    assert [row["id"] for row in agent_store.list_agents(folder)] == ["calc", "ember"]
    assert not list(folder.rglob("*.tmp"))


def test_create_refuses_duplicate_bad_id_port_clash_and_unknown_gateway(folder):
    with pytest.raises(AgentStoreError) as dup:
        agent_store.create_agent("ember", _cfg(9101), folder)
    assert dup.value.status == 409
    with pytest.raises(AgentStoreError):
        agent_store.create_agent("Bad Id", _cfg(9101), folder)
    with pytest.raises(AgentStoreError, match="port 9100"):
        agent_store.create_agent("calc", _cfg(9100), folder)
    with pytest.raises(AgentStoreError, match="gateway"):
        agent_store.create_agent("calc", {"port": 9103, "llm": {"provider": "anthropic", "gateway": "nope"}}, folder)
    with pytest.raises(AgentStoreError, match="llm.provider"):
        agent_store.create_agent("calc", {"port": 9103, "llm": {"provider": "x"}}, folder)
    assert not (folder / ".overrides").exists()


def test_second_entry_agent_is_refused(folder):
    with pytest.raises(AgentStoreError, match="already the entry"):
        agent_store.create_agent("calc", _cfg(9103, entry=True), folder)


def test_update_never_touches_the_tracked_file(folder):
    tracked = (folder / "ember.json").read_text()
    agent_store.update_agent("ember", _cfg(9100, entry=True, persona="local"), folder)
    assert (folder / "ember.json").read_text() == tracked
    assert agent_store.get_agent("ember", folder)["persona"] == "local"
    assert agent_spec.load_file(folder / "ember.json").persona == "local"


def test_update_replaces_agent_and_keeps_own_port(folder):
    agent_store.create_agent("calc", _cfg(9103), folder)
    agent_store.update_agent("calc", _cfg(9103, persona="hi"), folder)
    assert agent_store.get_agent("calc", folder)["persona"] == "hi"
    with pytest.raises(AgentStoreError) as missing:
        agent_store.update_agent("ghost", _cfg(9150), folder)
    assert missing.value.status == 404


def test_cannot_unset_the_only_entry_agent(folder):
    with pytest.raises(AgentStoreError, match="entry"):
        agent_store.update_agent("ember", _cfg(9100, entry=False), folder)


def test_delete_removes_file_and_override_but_not_the_entry_agent(folder):
    (folder / "calc.json").write_text(json.dumps(_cfg(9103)), encoding="utf-8")
    agent_store.update_agent("calc", _cfg(9103, persona="x"), folder)
    agent_store.delete_agent("calc", folder)
    assert not (folder / "calc.json").exists()
    assert "calc" not in _overrides(folder)
    with pytest.raises(AgentStoreError, match="entry agent"):
        agent_store.delete_agent("ember", folder)
    with pytest.raises(AgentStoreError) as missing:
        agent_store.delete_agent("calc", folder)
    assert missing.value.status == 404


def test_reset_drops_the_override_and_restores_the_tracked_file(folder):
    agent_store.update_agent("ember", _cfg(9100, entry=True, persona="local"), folder)
    listed = {row["id"]: row for row in agent_store.list_agents(folder)}
    assert listed["ember"]["overridden"] is True
    reset = agent_store.reset_agent("ember", folder)
    assert reset["overridden"] is False
    assert "persona" not in reset
    assert "persona" not in agent_store.get_agent("ember", folder)
    assert agent_store.list_agents(folder)[0]["overridden"] is False
    assert (folder / "ember.json").is_file()


def test_reset_refuses_without_an_override_or_a_tracked_default(folder):
    with pytest.raises(AgentStoreError, match="already uses its default") as plain:
        agent_store.reset_agent("ember", folder)
    assert plain.value.status == 409
    agent_store.create_agent("calc", _cfg(9103), folder)
    assert agent_store.list_agents(folder)[0]["overridden"] is False
    with pytest.raises(AgentStoreError, match="no default file"):
        agent_store.reset_agent("calc", folder)
    with pytest.raises(AgentStoreError, match="already uses its default"):
        agent_store.reset_agent("ghost", folder)


def test_gateway_catalog_lists_providers_and_local_laya():
    catalog = agent_store.gateway_catalog()
    assert {"anthropic", "openai", "laya"} <= set(catalog)
    assert any(g["id"] == "openrouter" for g in catalog["anthropic"])
    assert catalog["laya"][0]["id"] == "local"
    assert "api_key" not in json.dumps(catalog)
