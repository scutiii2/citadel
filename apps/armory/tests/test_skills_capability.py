"""The skills capability through its real MCP tools."""

from __future__ import annotations

import asyncio
import dataclasses
import sys

import pytest
from mcp.server.fastmcp import FastMCP

from src import commands
from src.config import settings
from src.services import capability_meta, capability_registry, identity_context, skill_store
from src.services.capability_loader import CapabilityLoader


@pytest.fixture
def capability(tmp_path, monkeypatch):
    import src.server

    server = FastMCP("skills-test")
    monkeypatch.setattr(src.server, "mcp", server)
    monkeypatch.setattr(capability_registry, "_REGISTRY", {})
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})
    monkeypatch.setattr(commands, "_COMMANDS", {})
    config = tmp_path / "capabilities.json"
    config.write_text("{}")
    loader = CapabilityLoader(server, "src.capabilities", config)
    loader.scan()
    asyncio.run(loader.set_online("skills", True))
    # The loader re-imports the capability, so patch the live module, not a stale import.
    domain = sys.modules["src.capabilities.skills.domain"]
    # Pin the exposure inputs, so a developer's MCP_HOST or token in .env cannot change the result.
    monkeypatch.setattr(
        domain, "settings",
        dataclasses.replace(settings, skills_db_path=tmp_path / "skills.db", host="127.0.0.1", internal_api_token=""),
    )
    monkeypatch.setattr(identity_context, "current_uid", lambda: "uid-alice")
    server.db = tmp_path / "skills.db"
    server.domain = domain
    return server


def call(server, name, args):
    return asyncio.run(server.call_tool(name, args))[1]


PROPOSAL = {"title": "Restart an app", "when_to_use": "an app is hung", "steps": "stop it, then start it"}


def test_propose_then_search_only_after_the_user_approves(capability):
    proposed = call(capability, "tool_skill_propose", PROPOSAL)
    assert proposed["id"] == 1 and "until the user approves" in proposed["message"]

    assert call(capability, "tool_skill_search", {"query": "restart"})["count"] == 0

    skill_store.set_status(capability.db, "uid-alice", 1, "active")
    found = call(capability, "tool_skill_search", {"query": "restart"})
    assert found["count"] == 1
    # ai_agent-side recall will rely on this first line.
    assert found["message"].startswith("1 approved skill(s):")
    assert "stop it, then start it" in found["message"]


def test_mark_records_an_outcome_for_an_approved_skill_only(capability):
    call(capability, "tool_skill_propose", PROPOSAL)
    assert call(capability, "tool_skill_mark", {"skill_id": 1, "outcome": "success"})["recorded"] is False
    skill_store.set_status(capability.db, "uid-alice", 1, "active")
    result = call(capability, "tool_skill_mark", {"skill_id": 1, "outcome": "failure"})
    assert result["recorded"] and "1 failed" in result["message"]


def test_the_model_has_no_tool_that_approves(capability):
    names = {tool.name for tool in asyncio.run(capability.list_tools())}
    assert {n for n in names if n.startswith("tool_skill_")} == {"tool_skill_propose", "tool_skill_search", "tool_skill_mark"}


def test_a_stranger_sees_nothing(capability, monkeypatch):
    call(capability, "tool_skill_propose", PROPOSAL)
    skill_store.set_status(capability.db, "uid-alice", 1, "active")
    monkeypatch.setattr(identity_context, "current_uid", lambda: "uid-bob")
    assert call(capability, "tool_skill_search", {"query": "restart"})["count"] == 0
    assert call(capability, "tool_skill_mark", {"skill_id": 1, "outcome": "success"})["recorded"] is False


def test_refuses_without_identity(capability, monkeypatch):
    monkeypatch.setattr(identity_context, "current_uid", lambda: "")
    with pytest.raises(Exception, match="no account identity|identity"):
        call(capability, "tool_skill_propose", PROPOSAL)


def test_refuses_when_exposed_without_a_token(capability, monkeypatch):
    exposed = dataclasses.replace(capability.domain.settings, host="0.0.0.0", internal_api_token="")
    monkeypatch.setattr(capability.domain, "settings", exposed)
    with pytest.raises(Exception, match="INTERNAL_API_TOKEN"):
        call(capability, "tool_skill_search", {"query": "x"})
    assert not capability.db.exists()
