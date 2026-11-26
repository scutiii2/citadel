from types import SimpleNamespace

from mcp.types import CallToolResult, TextContent

from src.agents.agent_spec import ToolScope
from src.providers.decision.contract import DecisionError
from src.runtime import approvals
from src.tools.mcp_client import mcp_upstream


def test_public_search_sends_only_snippets_to_jev_and_flags_injection(monkeypatch):
    snippets = "Untrusted web snippet"
    query = "private search query"
    calls = []

    def decide(provider, text, questions, **kwargs):
        calls.append((provider, text))
        return {"answers": {"injection": {"noul": 0.98, "uncertain": False}}}

    result = CallToolResult(
        content=[TextContent(type="text", text=f"{query}: {snippets}")],
        structured_content={"query": query, "results": [{"snippet": snippets}]},
    )
    monkeypatch.setattr(mcp_upstream.client, "call_tool", lambda *args, **kwargs: result)
    monkeypatch.setattr(mcp_upstream.agent_spec, "current", lambda: SimpleNamespace(tools=ToolScope()))
    monkeypatch.setattr(mcp_upstream.gateway_client, "decide", decide)
    policy = approvals.ApprovalPolicy()
    token = approvals.bind(policy)
    try:
        screened = mcp_upstream.call_tool("main__tool_web_search", {"query": query})
        assert "possible prompt injection" in screened
        assert screened.endswith(f"{query}: {snippets}")
        assert policy.needs_approval("main__tool_anything")
        assert calls == [("jev", snippets)]
    finally:
        approvals.reset(token)


def test_local_screen_keeps_output_when_gateway_is_unavailable(monkeypatch):
    original = "private extension output"

    def unavailable(provider, text, questions, **kwargs):
        assert provider == "laya" and text == original
        raise DecisionError("unavailable")

    monkeypatch.setattr(mcp_upstream.gateway_client, "decide", unavailable)
    assert mcp_upstream._screen_output(original) == original
