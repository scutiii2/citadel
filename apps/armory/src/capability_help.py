"""Structured `/<capability> help` data behind GET /commands/help and /commands/help/{capability}.
Each capability keeps a hand-maintained `help.json` beside its README (schema: `capabilities/README.md`); served by `help_routes.py`, not a tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.services import capability_meta, capability_registry

_CAPABILITIES_DIR = Path(__file__).resolve().parent / "capabilities"

_TARGETS = {"all", "tools", "commands", "workflow"}


class HelpError(Exception):
    """A user-facing problem resolving `/<capability> help`: unknown capability, missing help.json, or unknown target/command.
    The message is safe to show verbatim in the chat log."""


def _label(capability_id: str) -> str:
    try:
        return capability_registry.label(capability_id)
    except KeyError:
        return capability_id


def _load(capability_id: str) -> dict[str, Any]:
    folder = capability_meta.folder_for_id(capability_id)
    if folder is None:
        raise HelpError(f"Unknown capability {capability_id!r}")
    path = _CAPABILITIES_DIR / folder / "help.json"
    if not path.exists():
        raise HelpError(f"No help available for capability {capability_id!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def _tool_row(capability_id: str, tool: dict[str, Any]) -> dict[str, Any]:
    commands = tool.get("commands") or []
    slash_commands = ", ".join(f"/{capability_id} {name}" for name in commands) or "none (MCP-only)"
    return {
        "tool": tool["name"],
        "purpose": tool["purpose"],
        "connection": tool["connection"],
        "slash_command": slash_commands,
    }


def _param_text(param: dict[str, Any]) -> str:
    if param["required"]:
        qualifier = "required"
    elif param.get("default") is None:
        qualifier = "optional"
    else:
        qualifier = f"optional, default {param['default']!r}"
    return f"{param['name']} ({qualifier}) - {param['description']}"


def _command_row(capability_id: str, command: dict[str, Any]) -> dict[str, Any]:
    params = command.get("params") or []
    return {
        "slash_command": f"/{capability_id} {command['name']}",
        "parameters": "; ".join(_param_text(p) for p in params) or "None.",
    }


def _workflow_row(step: dict[str, Any]) -> dict[str, Any]:
    row = {"sequence": step["sequence"], "tool": step["tool"], "explanation": step["explanation"]}
    if step.get("ai_only_step"):
        row["ai_only_step"] = "Yes"
    return row


def _find_command(data: dict[str, Any], command_name: str) -> dict[str, Any]:
    for command in data.get("commands") or []:
        if command["name"] == command_name:
            return command
    known = ", ".join(sorted(c["name"] for c in data.get("commands") or [])) or "(none)"
    raise HelpError(f"Unknown command {command_name!r}. Available: {known}")


def build_index() -> dict[str, Any]:
    """The JSON body of `GET /commands/help`: one row per enabled built-in capability, for chat_app's `/help`.
    Skips a capability with no `help.json` instead of raising."""
    rows: list[dict[str, Any]] = []
    for name in sorted(capability_registry.names()):
        if not capability_registry.is_enabled(name):
            continue
        folder = capability_meta.folder_for_id(name)
        if folder is None:
            continue
        path = _CAPABILITIES_DIR / folder / "help.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        command_names = sorted({c["name"] for c in data.get("commands") or []} | {"help"})
        rows.append(
            {
                "capability": f"/{name}",
                "label": _label(name),
                "summary": data.get("summary", ""),
                "commands": ", ".join(command_names),
            }
        )
    return {
        "message": "Every capability listed below also answers `/<capability> help` for its full "
        "tool/command/workflow detail, or `/<capability> help command=<name>` for one command.",
        "capabilities": rows,
    }


def build_help(capability_id: str, target: str = "all", command: str | None = None) -> dict[str, Any]:
    """The JSON body of `GET /commands/help/{capability}`: a `message` plus `list[dict]` fields, rendered by chat_app's generic formatter.
    `command` takes priority over `target`; raises `HelpError` for an unknown capability, target or command."""
    data = _load(capability_id)
    label = _label(capability_id)

    if command:
        cmd = _find_command(data, command)
        tool = next((t for t in data.get("tools") or [] if t["name"] == cmd["tool"]), None)
        message = f"`/{capability_id} {command}`"
        if tool is not None:
            message += f" - {tool['purpose']}"
        result: dict[str, Any] = {"message": message, "commands": [_command_row(capability_id, cmd)]}
        if tool is not None:
            result["tools"] = [_tool_row(capability_id, tool)]
        steps = [_workflow_row(s) for s in data.get("workflow") or [] if s.get("tool") == cmd["tool"]]
        if steps:
            result["workflow"] = steps
        return result

    if target not in _TARGETS:
        raise HelpError(f"Unknown help target {target!r}. Expected one of: {', '.join(sorted(_TARGETS))}")

    summary = data.get("summary", "")
    result = {"message": f"**/{capability_id}** - {label}\n\n{summary}".strip()}
    if target in {"all", "tools"}:
        result["tools"] = [_tool_row(capability_id, t) for t in data.get("tools") or []]
    if target in {"all", "commands"}:
        result["commands"] = [_command_row(capability_id, c) for c in data.get("commands") or []]
    if target in {"all", "workflow"}:
        result["workflow"] = [_workflow_row(s) for s in data.get("workflow") or []]
    return result
