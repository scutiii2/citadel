from types import SimpleNamespace

from src.services.turns import _trace_parts
from src.services.usage_service import usage_rows


def test_router_attempt_trace_keeps_outcomes_without_prompt_or_keys():
    rows = [{"agent_id": "router", "provider_id": "laya", "model": "typed-decisions",
        "total_tokens": 10, "routing": {"ok": True, "reason": "", "duration_ms": 2,
            "agent_choice": "ops", "agent_uncertain": False, "policy_revision": "revision",
            "api_key": "must-not-appear", "subject": "private question"}} for _ in range(24)]
    agents, prompts = _trace_parts({"agent_usage": rows}, SimpleNamespace(steps=[]))
    assert len(agents) == 24
    assert agents[0]["routing"]["agent_choice"] == "ops"
    assert "api_key" not in agents[0]["routing"] and "subject" not in agents[0]["routing"]
    assert prompts == []
    assert sum(row["total_tokens"] for row in usage_rows({"agent_usage": rows})) == 240
