"""Registry for chat-invocable commands (tools opted in via @command), separate from FastMCP's registration.
Capability id comes from the module path via capability_meta.py, falling back to the folder name."""

from __future__ import annotations

from dataclasses import dataclass

from src.services import capability_meta


@dataclass(frozen=True)
class CommandSpec:
    capability: str
    name: str
    description: str
    tool_name: str


_COMMANDS: dict[tuple[str, str], CommandSpec] = {}


def _infer_capability(module_name: str) -> str:
    parts = module_name.split(".")
    if "capabilities" in parts:
        index = parts.index("capabilities")
        if index + 1 < len(parts):
            folder = parts[index + 1]
            meta = capability_meta.for_folder(folder)
            return meta.id if meta is not None else folder
    raise ValueError(
        f"Cannot infer a capability id from module {module_name!r} - "
        "@command must decorate a function defined inside a "
        "src.capabilities.<name> package."
    )


def command(name: str, description: str, capability: str | None = None):
    """Mark an @mcp.tool() function as invocable from chat as `/<capability> <name> key=value ...`; only records metadata.
    `capability` is normally inferred from capability_meta.py; it must match the id passed to `capability_registry.capturing()` in run.py."""

    def decorator(fn):
        capability_id = capability or _infer_capability(fn.__module__)
        _COMMANDS[(capability_id, name)] = CommandSpec(
            capability=capability_id, name=name, description=description, tool_name=fn.__name__
        )
        return fn

    return decorator


def all_commands() -> list[CommandSpec]:
    return list(_COMMANDS.values())


def remove_capability(capability_id: str) -> None:
    """Drop every command of one capability, so a reload can register them
    again without tripping over its own earlier entries."""
    for key in [key for key in _COMMANDS if key[0] == capability_id]:
        del _COMMANDS[key]
