"""The Router agent's model list, for what decides on its behalf: automatic tier, automatic routing and the
orchestrator's secret check."""

from __future__ import annotations

from src.agents import agent_registry, agent_spec


def router_models() -> tuple[str, ...]:
    spec = agent_spec.current()
    if getattr(spec, "internal_role", None) == "router":
        return spec.llm.gateway_names
    for record in agent_registry.read_definitions():
        if record.get("role") == "router" and record.get("enabled", True):
            llm = record.get("llm") if isinstance(record.get("llm"), dict) else {}
            names = tuple(name for name in (llm.get("gateway"), *(llm.get("fallbacks") or ()))
                          if isinstance(name, str) and name)
            if names:
                return names
    return agent_spec.DEFAULT_DECISION_MODELS
