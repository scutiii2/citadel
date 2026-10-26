import asyncio

from src.agents.roles.router import router_client
from src.agents import agent_registry
from src.agents.roles.router.router_contract import RouteRequest
from src.runtime import internal_auth


def test_disabled_or_absent_router_returns_no_decision(monkeypatch):
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "all_agents", lambda: [])
    assert asyncio.run(router_client.decide(RouteRequest(subject="hello", request_id="r"))) is None


def test_missing_token_never_contacts_router(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "")
    assert asyncio.run(router_client.decide(RouteRequest(subject="hello", request_id="r"))) is None


def test_unknown_target_abstains(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "token")
    monkeypatch.setattr(agent_registry, "reload", lambda: None)
    monkeypatch.setattr(agent_registry, "all_agents", lambda: [{"id": "router", "role": "router",
        "url": "http://local/mcp", "decision": {"deadline_seconds": 1}}])
    async def call(*args):
        return {"policy_revision": "r", "agent": {"choice": "unknown", "uncertain": False}}
    monkeypatch.setattr(router_client, "_call", call)
    assert asyncio.run(router_client.decide(RouteRequest(subject="hello", request_id="r"))) is None
