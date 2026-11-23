import pytest

from src.gateway.conversation.contract import Limits, parse_request
from src.gateway.conversation.errors import GatewayError
from tests.gateway.conversation.helpers import LIMITS, chat

PNG = "aGVsbG8="


def refused(**fields):
    with pytest.raises(GatewayError) as error:
        chat(**fields)
    assert error.value.status == 422 and error.value.code == "invalid_request"
    return error.value.message


def test_string_content_is_one_text_block():
    request = chat()
    assert request.messages == [{"role": "user", "content": [{"type": "text", "text": "Hi"}]}]
    assert request.uses == set() and request.tool_choice is None and request.cache is False and request.stream is False


def test_full_request_is_normalized():
    request = chat(
        system="Be brief", model="m", max_tokens=100, temperature=0.5, cache=True, stream=True,
        messages=[
            {"role": "user", "content": [{"type": "text", "text": "Look"}, {"type": "image", "media_type": "image/png", "data": PNG}]},
            {"role": "assistant", "content": [{"type": "tool_call", "id": "c1", "name": "get_time", "arguments": {}}], "reasoning_state": "x"},
            {"role": "tool", "content": [{"type": "tool_result", "id": "c1", "text": "12:00"}]},
        ],
        tools=[{"name": "get_time"}], reasoning={"effort": "low"})
    assert request.messages[2]["content"][0]["is_error"] is False
    assert request.tools == [{"name": "get_time", "description": "", "parameters": {"type": "object", "properties": {}}}]
    assert request.tool_choice == "auto"
    assert request.reasoning == {"effort": "low", "budget_tokens": None}
    assert request.uses == {"images", "tools", "reasoning"}


def test_reasoning_defaults_to_medium_when_empty():
    assert chat(reasoning={}).reasoning == {"effort": "medium", "budget_tokens": None}


def test_unknown_fields_are_refused():
    assert "unexpected" in refused(unexpected=1)
    refused(messages=[{"role": "user", "content": [{"type": "text", "text": "x", "extra": 1}]}])


@pytest.mark.parametrize("fields", [
    {"messages": []},
    {"messages": [{"role": "system", "content": "x"}]},
    {"messages": [{"role": "user", "content": [{"type": "tool_call", "id": "a", "name": "n", "arguments": {}}]}]},
    {"messages": [{"role": "user", "content": [{"type": "text", "text": ""}]}]},
    {"messages": [{"role": "user", "content": [{"type": "image", "media_type": "image/tiff", "data": PNG}]}]},
    {"messages": [{"role": "user", "content": "x", "reasoning_state": "s"}]},
    {"tools": [{"name": "bad name"}]},
    {"tools": [{"name": "a"}, {"name": "a"}]},
    {"tool_choice": "required"},
    {"tools": [{"name": "a"}], "tool_choice": {"name": "b"}},
    {"tools": [{"name": "a"}], "schema": {"name": "s", "schema": {}}},
    {"reasoning": {"effort": "extreme"}},
    {"reasoning": {"budget_tokens": 0}},
    {"max_tokens": 0}, {"max_tokens": True}, {"temperature": 3}, {"cache": "yes"}, {"stream": 1},
])
def test_bad_requests(fields):
    refused(**fields)


def test_limits():
    small = Limits(max_messages=1, max_text=5, max_tools=1, max_images=1, max_image_bytes=4)
    base = {"gateway": "g", "messages": [{"role": "user", "content": "Hi"}]}
    for body in (
        {**base, "messages": base["messages"] * 2},
        {**base, "messages": [{"role": "user", "content": "toolong"}]},
        {**base, "tools": [{"name": "a"}, {"name": "b"}]},
        {**base, "messages": [{"role": "user", "content": [{"type": "image", "media_type": "image/png", "data": "A" * 8}]}]},
    ):
        with pytest.raises(GatewayError) as error:
            parse_request(body, small)
        assert error.value.status == 422


def test_gateway_is_required():
    with pytest.raises(GatewayError):
        parse_request({"messages": [{"role": "user", "content": "x"}]}, LIMITS)
