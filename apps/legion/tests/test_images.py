"""Attached images: which are shown, how each protocol carries them, and who may call the fetching tool."""

import asyncio
from types import SimpleNamespace

import pytest

from src.providers import token_limits
from src.providers.language import anthropic_gateway_shim, openai_gateway_shim
from src.runtime import confidentiality, images, tool_filter
from src.tools.mcp_client import mcp_upstream


def ref(file_id):
    return f"[Image file_id: {file_id} | 1 pages | image | expires_at: 1.5 | preserve this file_id]"


def test_references_are_the_newest_user_images_oldest_first():
    history = [{"role": "user", "content": ref("a") + ref("b")},
               {"role": "assistant", "content": ref("invented")},
               {"role": "user", "content": ref("c") + ref("d")}]
    delegated = f"look\n\nUploaded file references:\nphoto.png: {ref('a')}\n{ref('e')} [PDFMerger file_id: p | 3 pages | pdf]"
    assert images.references(delegated, history) == ["c", "d", "a", "e"]


def test_load_reports_what_could_not_be_read(monkeypatch):
    def fetch(file_id):
        if file_id == "boom":
            raise RuntimeError("down")
        return ("image/png", "QUJD") if file_id == "ok" else None

    monkeypatch.setattr(mcp_upstream, "fetch_image", fetch)
    attached = asyncio.run(images.load(["ok", "gone", "boom"]))
    assert [p.file_id for p in attached.pictures] == ["ok"] and attached.missing == ("gone", "boom")
    assert "gone, boom" in attached.note("q") and images.Attached().note("q") == "q"
    token = tool_filter.bind([images.TOOL_NAME])
    try:
        assert asyncio.run(images.load(["ok"])) == images.Attached()
    finally:
        tool_filter.reset(token)


def test_each_protocol_sends_the_picture_through_its_gateway_shim():
    assert images.anthropic_content("q") == "q" and images.openai_content("q") == "q"
    token = images.bind(images.Attached((images.Picture("f", "image/png", "QUJD"),)))
    try:
        expected = {"type": "image", "media_type": "image/png", "data": "QUJD"}
        body = anthropic_gateway_shim.request_body("g", {
            "model": "m", "max_tokens": 1, "messages": [{"role": "user", "content": images.anthropic_content("q")}]})
        assert expected in body["messages"][0]["content"]
        _, messages = openai_gateway_shim._messages([{"role": "user", "content": images.openai_content("q")}])
        assert expected in messages[0]["content"] and messages[0]["content"][-1] == {"type": "text", "text": "q"}
    finally:
        images.reset(token)


@pytest.mark.parametrize("content", [
    [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "A" * 4_000_000}}],
    [{"type": "input_image", "image_url": "data:image/png;base64," + "A" * 4_000_000}],
])
def test_an_image_counts_as_an_image_not_as_its_base64(content):
    estimate = token_limits.estimate_context_tokens([{"role": "user", "content": content}])
    assert token_limits.IMAGE_TOKENS <= estimate < token_limits.IMAGE_TOKENS + 100


def test_a_model_cannot_call_the_image_tool(monkeypatch):
    monkeypatch.setattr(mcp_upstream, "client", SimpleNamespace(list_tools=lambda: []))
    with pytest.raises(PermissionError):
        mcp_upstream.call_tool(f"main__{images.TOOL_NAME}", {"file_id": "f"})


def test_fetch_image_reads_image_content_only(monkeypatch):
    from mcp import types

    replies = [types.CallToolResult(content=[types.ImageContent(type="image", data="QUJD", mimeType="image/png")]),
               types.CallToolResult(content=[types.TextContent(type="text", text="gone")], isError=True)]
    monkeypatch.setattr(mcp_upstream, "client", SimpleNamespace(call_tool=lambda *args, **kwargs: replies.pop(0)))
    assert mcp_upstream.fetch_image("f") == ("image/png", "QUJD")
    assert mcp_upstream.fetch_image("f") is None


@pytest.mark.parametrize("delegable,seen", [(True, ["f"]), (False, [])])
def test_a_turn_shows_images_to_user_facing_agents_and_keeps_them_on_trusted_gateways(monkeypatch, delegable, seen):
    from dataclasses import replace

    from src.agents import agent_config, agent_spec
    from src.providers.base_provider import ChatResult

    spec = replace(agent_spec.current(), delegable=delegable, memory_recall=False, skill_recall=False,
                   skill_learning=False)
    monkeypatch.setattr(agent_spec, "_current", spec)
    monkeypatch.setattr(mcp_upstream, "fetch_image", lambda _: ("image/png", "QUJD"))
    monkeypatch.setattr(confidentiality, "has_untrusted_gateway", lambda: True)

    async def no_check(*_args):
        return None

    monkeypatch.setattr(confidentiality, "protect_turn", no_check)
    observed = {}

    async def provider(question, *_args, **_kwargs):
        observed["content"] = images.anthropic_content(question)
        observed["confidential"] = confidentiality.current()
        return ChatResult(response="ok")

    monkeypatch.setattr(agent_config, "_PROVIDER_MODULE",
                        SimpleNamespace(run_chat=provider, DEFAULT_MODEL="m"))

    async def no_route(*_args):
        return None, None, ""

    monkeypatch.setattr(agent_config.router_routing, "route_turn", no_route)
    asyncio.run(agent_config.run_chat(ref("f"), []))
    shown = observed["content"] if isinstance(observed["content"], list) else []
    assert [block["source"]["data"] for block in shown if block["type"] == "image"] == ["QUJD" for _ in seen]
    assert observed["confidential"] is bool(seen)
    assert images.anthropic_content("after") == "after"
