"""`run_tools`: several tool calls in one model step, with dependencies between them.

The model submits a list of steps. Steps with no dependency on each other run in the same wave
(tool_batch.ToolRound decides what may overlap); a step that needs another step's output names it
with `{"$ref": "id"}` (the whole result) or `{"$ref": "id.field.0"}` (a field of a JSON result). The
model receives one reply: only the steps it marked `return` (by default, the last ones) come back in
full, the others as a status line. This module holds the schema, the validation and the pure helpers;
running the steps is ToolRound's job, so every step keeps the guard, the approvals and the step events
of an ordinary call.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from src.agents import agent_spec
from src.agents.roles.orchestrator import submit_plan
from src.runtime import tool_batch_settings

TOOL_NAME = "run_tools"
_ID_CHARS = 64


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    arguments: dict[str, Any]
    depends_on: tuple[str, ...]
    returned: bool | None  # None: the default (a step nothing else depends on)


def enabled() -> bool:
    """Offered to a specialist that has tools; the orchestrator plans, and architects and routers have none."""
    return (getattr(agent_spec.current(), "role", None) == "specialist" and not submit_plan.enabled()
            and tool_batch_settings.current().batch_tool)


def batchable(names: Collection[str], local: Collection[str]) -> frozenset[str]:
    """The tools a step may call: every offered tool except the agent's local ones (this one included)."""
    return frozenset(name for name in names if name not in local and name != TOOL_NAME)


def tool_description() -> str:
    return (
        "Run two or more tool calls in one step when you already know all of them. Calls that do not depend on "
        "each other run at the same time. To use one step's output as an argument of another, give that argument "
        '{"$ref": "step_id"} (the whole result) or {"$ref": "step_id.field"} (a field of a JSON result); the second '
        "step then waits for the first. A step that fails makes the steps that need it skip. Only steps with "
        '"return": true (by default, the steps nothing else uses) come back in full; the others return a status '
        f"line, so ask for the ones you need to read. Use at most {tool_batch_settings.current().max_steps} steps. Use a single tool call for one call, "
        "and separate calls when a later call depends on what you learn from an earlier one."
    )


def tool_parameters() -> dict[str, Any]:
    return {
        "type": "object", "required": ["steps"], "additionalProperties": False,
        "properties": {"steps": {
            "type": "array", "minItems": 1, "maxItems": tool_batch_settings.current().max_steps,
            "items": {
                "type": "object", "required": ["id", "tool", "arguments"], "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "minLength": 1, "maxLength": _ID_CHARS},
                    "tool": {"type": "string", "minLength": 1, "maxLength": 200},
                    "arguments": {"type": "object"},
                    "return": {"type": "boolean"},
                },
            },
        }},
    }


def _refs(value: Any) -> list[str]:
    """The `$ref` targets inside `value`, as written (`id` or `id.path`)."""
    if isinstance(value, dict):
        if set(value) == {"$ref"} and isinstance(value["$ref"], str):
            return [value["$ref"]]
        return [ref for item in value.values() for ref in _refs(item)]
    if isinstance(value, list):
        return [ref for item in value for ref in _refs(item)]
    return []


def validate(arguments: Any, tools: Collection[str],
             known: Collection[str] = ()) -> tuple[list[Step] | None, list[list[Step]] | None, str | None]:
    """The steps, their waves, and an error text. `known` holds ids of earlier batches a ref may use."""
    if not isinstance(arguments, dict) or not isinstance(arguments.get("steps"), list):
        return None, None, "run_tools needs a steps list."
    extra = set(arguments) - {"steps"}
    if extra:
        return None, None, f"run_tools unknown field: {sorted(extra)[0]}."
    raw = arguments["steps"]
    limit = tool_batch_settings.current().max_steps
    if not 1 <= len(raw) <= limit:
        return None, None, f"run_tools needs 1 to {limit} steps."
    ids: list[str] = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            ids.append(item["id"])
    steps: list[Step] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            return None, None, f"Step {index + 1} must be an object."
        unknown = set(item) - {"id", "tool", "arguments", "return"}
        if unknown:
            return None, None, f"Step {index + 1} unknown field: {sorted(unknown)[0]}."
        step_id, tool, step_arguments = item.get("id"), item.get("tool"), item.get("arguments")
        if not isinstance(step_id, str) or not 0 < len(step_id) <= _ID_CHARS or ":" in step_id or "." in step_id:
            return None, None, f"Step {index + 1} needs an id of 1 to {_ID_CHARS} characters without '.' or ':'."
        if ids.count(step_id) > 1:
            return None, None, f"Duplicate step id {step_id!r}."
        if tool not in tools:
            return None, None, f"Step {step_id!r}: {tool!r} is not a tool you can run here."
        if not isinstance(step_arguments, dict):
            return None, None, f"Step {step_id!r}: arguments must be an object."
        if "return" in item and not isinstance(item["return"], bool):
            return None, None, f"Step {step_id!r}: return must be true or false."
        depends: list[str] = []
        for ref in _refs(step_arguments):
            target = ref.split(".", 1)[0]
            if target == step_id:
                return None, None, f"Step {step_id!r} refers to itself."
            if target in ids:
                if target not in depends:
                    depends.append(target)
            elif target not in known:
                return None, None, f"Step {step_id!r} refers to unknown step {target!r}."
        steps.append(Step(step_id, tool, step_arguments, tuple(depends), item.get("return")))
    waves: list[list[Step]] = []
    done: set[str] = set()
    remaining = list(steps)
    while remaining:
        wave = [step for step in remaining if set(step.depends_on) <= done]
        if not wave:
            return None, None, "run_tools steps depend on each other in a cycle: " + ", ".join(step.id for step in remaining)
        waves.append(wave)
        done |= {step.id for step in wave}
        remaining = [step for step in remaining if step.id not in done]
    return steps, waves, None


def resolve(value: Any, results: Mapping[str, str]) -> Any:
    """`value` with each `$ref` replaced by the result it names. Raises ValueError when it cannot be read."""
    if isinstance(value, dict):
        if set(value) == {"$ref"} and isinstance(value["$ref"], str):
            return _lookup(value["$ref"], results)
        return {key: resolve(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, results) for item in value]
    return value


def _lookup(ref: str, results: Mapping[str, str]) -> Any:
    target, _, path = ref.partition(".")
    if target not in results:
        raise ValueError(f"Result {target!r} is not available.")
    text = results[target]
    if not path:
        return text
    try:
        node: Any = json.loads(text)
    except ValueError:
        raise ValueError(f"Result {target!r} is not JSON, so {ref!r} cannot be read.") from None
    for part in path.split("."):
        try:
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError(f"Result {target!r} has no {path!r}.") from None
    return node


def reply(steps: list[Step], status: Mapping[str, str], texts: Mapping[str, str]) -> str:
    """The text the model receives: full results only for the steps it asked to see."""
    used = {dependency for step in steps for dependency in step.depends_on}
    each = tool_batch_settings.current().max_result_chars
    budget = tool_batch_settings.current().max_total_chars
    rows: dict[str, dict[str, Any]] = {}
    for step in steps:
        text = texts.get(step.id, "")
        row: dict[str, Any] = {"status": status[step.id]}
        shown = step.returned if step.returned is not None else step.id not in used
        if status[step.id] != "done" or shown:
            if len(text) > min(each, budget):
                text = text[:max(0, min(each, budget))]
                row["truncated"] = True
            budget -= len(text)
            row["result"] = text
        else:
            row["result_hidden"] = f"{len(text)} characters"
        rows[step.id] = row
    return json.dumps({"steps": rows, "note": 'A hidden result was used by later steps; set "return": true to read it.'},
                      ensure_ascii=False)


def summary(steps: list[Step], status: Mapping[str, str]) -> str:
    counts = [f"{sum(1 for step in steps if status[step.id] == name)} {name}" for name in ("done", "failed", "skipped")]
    return f"Ran {len(steps)} tools: " + ", ".join(count for count in counts if not count.startswith("0 "))
