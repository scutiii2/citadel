import asyncio

import pytest

from src.runtime import internal_auth


def test_requester_meta_carries_a_valid_chat_id(monkeypatch):
    monkeypatch.setattr(internal_auth, "requester_token", lambda: "signed")
    handle = internal_auth.bind_requester(internal_auth.Requester("ana", "a@x", "u-1", chat_id="chat-1"))
    try:
        assert internal_auth.requester_meta() == {"requester_token": "signed", "chat_id": "chat-1"}
    finally:
        internal_auth.reset_requester(handle)


def test_a_malformed_chat_id_is_dropped(monkeypatch):
    monkeypatch.setattr(internal_auth, "requester_token", lambda: "signed")
    handle = internal_auth.bind_requester(internal_auth.Requester("ana", "a@x", "u-1", chat_id="../x y"))
    try:
        assert "chat_id" not in internal_auth.requester_meta()
    finally:
        internal_auth.reset_requester(handle)


def test_no_chat_id_means_no_hint(monkeypatch):
    monkeypatch.setattr(internal_auth, "requester_token", lambda: "signed")
    assert "chat_id" not in internal_auth.requester_meta()


@pytest.mark.parametrize("chat_args, expected", [({}, ""), ({"chat_id": "chat-1"}, "chat-1")])
def test_ask_binds_the_optional_chat_id_only_during_the_turn(monkeypatch, chat_args, expected):
    from src import server
    from src.providers.base_provider import ChatResult

    async def run_chat(*args, **kwargs):
        assert internal_auth.current_requester().chat_id == expected
        return ChatResult(response="answer", model_executed=False)

    monkeypatch.setattr(server.agent_config, "run_chat", run_chat)
    async def run():
        schema = next(tool.inputSchema for tool in await server.mcp.list_tools() if tool.name == "ask")
        assert "chat_id" in schema["properties"] and "chat_id" not in schema["required"]
        assert (await server.ask("question", **chat_args))["response"] == "answer"
        assert not internal_auth.current_requester().chat_id

    asyncio.run(run())
