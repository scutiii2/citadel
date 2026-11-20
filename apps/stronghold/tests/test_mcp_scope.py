import pytest

from src.citadel_auth import AuthError
from src.citadel_auth.errors import Forbidden
from src.mcp_tools import scope as scope_module
from src.mcp_tools.scope import Scope, ScopeError, resolve_scope

CHAT = "chat-1"


class FakeChats:
    def __init__(self, owned):
        self.owned = owned

    async def exists(self, owner, chat_id):
        return (owner, chat_id) in self.owned


class FakeApp:
    class state:
        keyring = object()
        chats = FakeChats({("u-1", CHAT)})


def fake_context(monkeypatch, *, caller="legion", token="signed", meta=None, uid="u-1", error=None):
    """Stand in for the SDK request context and for requester_context."""
    from contextlib import asynccontextmanager

    class Meta:
        model_extra = meta if meta is not None else {"requester_token": token, "chat_id": CHAT}

    class Request:
        scope = {"citadel_auth": (type("Caller", (), {"name": caller})(), None, "header-token")}

    class Context:
        request, meta = Request(), Meta()

    monkeypatch.setattr(scope_module, "_request_context", lambda: Context())

    @asynccontextmanager
    async def requester_context(keyring, who, signed, audience):
        assert audience == "stronghold"
        if error is not None:
            raise error("test-only verification failure")
        yield type("Who", (), {"uid": uid})() if signed else None

    monkeypatch.setattr(scope_module, "requester_context", requester_context)


async def test_a_signed_requester_with_an_owned_chat_gives_a_scope(monkeypatch):
    fake_context(monkeypatch)
    async with resolve_scope(FakeApp) as scope:
        assert scope == Scope("u-1", CHAT)


@pytest.mark.parametrize("kwargs", [
    {"caller": "armory"},                  # only Legion may call
    {"token": ""},                         # no signed requester
    {"meta": {"requester_token": "t"}},    # no chat id
    {"meta": {"requester_token": "t", "chat_id": "other"}},  # chat the account does not own
    {"error": AuthError},
    {"error": Forbidden},
    {"meta": {"requester_token": "signed", "chat_id": CHAT + "\n"}},
    {"meta": {"requester_token": 42, "chat_id": CHAT}},
    {"uid": "u-2"},                        # requester of another account
])
async def test_everything_else_is_refused(monkeypatch, kwargs):
    fake_context(monkeypatch, **kwargs)
    with pytest.raises(ScopeError):
        async with resolve_scope(FakeApp):
            pass
