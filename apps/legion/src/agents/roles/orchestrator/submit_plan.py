"""submit_plan's local schema and validation of untrusted model arguments."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from src.agents import agent_spec
from src.agents.roles.architect.executor import validate_dag
from src.agents.roles.architect.types import Plan, Step

TOOL_NAME = "submit_plan"
MAX_STEPS = 8
MIN_BRIEF = 20
MAX_BRIEF = 16000


def enabled() -> bool:
    spec = agent_spec.current()
    return getattr(spec, "mode", "legacy") == "plan" and spec.orchestrator


def tool_description() -> str:
    return (
        "Submit a dependency plan to the architects in your catalog. Each brief must stand alone: "
        "include the user's file names, ids, requirements and needed context. Use at most 8 steps. "
        "For a direct answer, reply normally without submitting a plan."
    )


def tool_parameters() -> dict[str, Any]:
    return {
        "type": "object", "required": ["steps"], "additionalProperties": False,
        "properties": {"steps": {
            "type": "array", "minItems": 1, "maxItems": MAX_STEPS,
            "items": {
                "type": "object", "required": ["id", "architect", "brief", "depends_on"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "architect": {"type": "string", "minLength": 1, "maxLength": 64},
                    "brief": {"type": "string", "minLength": MIN_BRIEF, "maxLength": MAX_BRIEF},
                    "depends_on": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}},
                },
            },
        }},
    }


def validate(arguments: Any, architect_ids: Collection[str], max_steps: int = MAX_STEPS, *,
             architect_kinds: Mapping[str, str | None] | None = None) -> tuple[Plan | None, str | None]:
    if not isinstance(arguments, dict) or not isinstance(arguments.get("steps"), list):
        return None, "submit_plan needs a steps list."
    unknown = set(arguments) - {"steps"}
    if unknown:
        return None, f"submit_plan unknown field: {sorted(unknown)[0]}."
    raw = arguments["steps"]
    if not 1 <= len(raw) <= max_steps:
        return None, f"submit_plan needs 1 to {max_steps} steps."
    steps = []
    for index, item in enumerate(raw):
        prefix = f"steps[{index}]"
        if not isinstance(item, dict):
            return None, f"{prefix}: each step must be an object."
        unknown = set(item) - {"id", "architect", "brief", "depends_on"}
        if unknown:
            return None, f"{prefix}: unknown field {sorted(unknown)[0]}."
        for key in ("id", "architect", "brief"):
            value = item.get(key)
            low, high = (MIN_BRIEF, MAX_BRIEF) if key == "brief" else (1, 64)
            if not isinstance(value, str) or not low <= len(value.strip()) <= high:
                return None, f"{prefix}.{key} must be a string of {low} to {high} characters."
        architect = item["architect"].strip()
        if architect not in architect_ids:
            return None, f"{prefix}.architect {architect!r} is not in this turn's catalog."
        dependencies = item.get("depends_on")
        if (not isinstance(dependencies, list)
                or not all(isinstance(key, str) and 1 <= len(key.strip()) <= 64 for key in dependencies)):
            return None, f"{prefix}.depends_on must be a list of step ids."
        steps.append(Step(item["id"].strip(), architect, item["brief"].strip(),
                          tuple(key.strip() for key in dependencies),
                          effect="read" if (architect_kinds or {}).get(architect) == "code" else "write"))
    try:
        validate_dag(steps)
    except ValueError as error:
        return None, str(error)
    return Plan(tuple(steps)), None
