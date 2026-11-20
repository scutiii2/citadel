import pytest

from src.citadel_auth import AuthError
from src.mcp_tools.scope import Account, ScopeError, resolve_account
from tests.test_mcp_scope import FakeApp, fake_context


async def test_a_signed_requester_gives_an_account_without_a_chat(monkeypatch):
    fake_context(monkeypatch, meta={"requester_token": "signed"})
    async with resolve_account(FakeApp) as account:
        assert account == Account("u-1")


async def test_a_chat_id_is_not_needed_and_not_trusted(monkeypatch):
    fake_context(monkeypatch, meta={"requester_token": "signed", "chat_id": "someone-elses"})
    async with resolve_account(FakeApp) as account:
        assert account == Account("u-1")


@pytest.mark.parametrize("kwargs", [
    {"caller": "armory"}, {"token": ""}, {"meta": {"requester_token": 42}}, {"error": AuthError},
])
async def test_everything_else_is_refused(monkeypatch, kwargs):
    fake_context(monkeypatch, **kwargs)
    with pytest.raises(ScopeError):
        async with resolve_account(FakeApp):
            pass

async def test_a_signed_header_can_supply_the_requester_without_metadata(monkeypatch):
    fake_context(monkeypatch, meta={})
    async with resolve_account(FakeApp) as account:
        assert account == Account("u-1")
