"""Live enable/disable for built-in capabilities.
FastMCP has no public way to remove a resource template (mcp==1.28.0), so this reaches into ``mcp._tool_manager``/``_resource_manager``. ``capturing(mcp, name)`` diffs what a block registered and stores the exact Tool/ResourceTemplate objects, so re-enabling restores their metadata."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources.templates import ResourceTemplate
from mcp.server.fastmcp.tools.base import Tool



@dataclass
class _CapabilityHandle:
    tools: list[Tool] = field(default_factory=list)
    resource_templates: list[ResourceTemplate] = field(default_factory=list)
    # True at capture time by construction: capturing() runs while the
    # tools/templates it just diffed are actually live on `mcp`.
    enabled: bool = True
    # Human-readable display name (see capability_meta.py); defaults to `name`.
    label: str = ""


_REGISTRY: dict[str, _CapabilityHandle] = {}


@contextmanager
def capturing(mcp: FastMCP, name: str, label: str | None = None) -> Iterator[None]:
    """Wrap a capability's import block; records whatever it registered by diffing ``mcp``'s tool/resource-template dicts.
    ``label`` is the display name exposed over ``GET /capabilities`` (see capability_meta.py); defaults to `name`."""
    if name in _REGISTRY:
        raise ValueError(f"Capability {name!r} is already registered")

    tools_before = set(mcp._tool_manager._tools)
    templates_before = set(mcp._resource_manager._templates)
    yield
    _REGISTRY[name] = _CapabilityHandle(
        tools=[tool for tname, tool in mcp._tool_manager._tools.items() if tname not in tools_before],
        resource_templates=[
            template
            for uri, template in mcp._resource_manager._templates.items()
            if uri not in templates_before
        ],
        label=label or name,
    )


def _handle(name: str) -> _CapabilityHandle:
    if name not in _REGISTRY:
        known = ", ".join(names()) or "none configured"
        raise KeyError(f"Unknown capability {name!r}. Registered: {known}.")
    return _REGISTRY[name]


def names() -> list[str]:
    return sorted(_REGISTRY)


def is_enabled(name: str) -> bool:
    return _handle(name).enabled


def label(name: str) -> str:
    return _handle(name).label


def tool_names(name: str) -> list[str]:
    """Every tool name captured for `name`, regardless of enabled state (stable across a toggle).
    Used by capability_routes.py to expose tool ownership over ``GET /capabilities``."""
    return sorted(tool.name for tool in _handle(name).tools)


def resource_names(name: str) -> list[str]:
    """Same as tool_names(), for resource templates, keyed by each template's `name` (function name, not URI)."""
    return sorted(
        template.name for template in _handle(name).resource_templates if getattr(template, "name", None)
    )


def set_enabled(mcp: FastMCP, name: str, enabled: bool) -> None:
    """Add or remove `name`'s tools/resource templates on the live `mcp` instance.
    No-op if `enabled` already matches, avoiding FastMCP's duplicate-tool warning."""
    handle = _handle(name)
    if enabled == handle.enabled:
        return

    if enabled:
        for tool in handle.tools:
            mcp._tool_manager._tools[tool.name] = tool
        for template in handle.resource_templates:
            mcp._resource_manager._templates[template.uri_template] = template
    else:
        for tool in handle.tools:
            mcp.remove_tool(tool.name)
        for template in handle.resource_templates:
            mcp._resource_manager._templates.pop(template.uri_template, None)

    handle.enabled = enabled


def register_unloaded(name: str, label: str) -> None:
    """Record a capability that exists on disk but is not online: an offline handle with no tools.
    Going online replaces it with a captured one (capability_loader.py)."""
    if name in _REGISTRY:
        raise ValueError(f"Capability {name!r} is already registered")
    _REGISTRY[name] = _CapabilityHandle(enabled=False, label=label)


def discard(mcp: FastMCP, name: str) -> None:
    """Take `name` off the live server and forget it. Used before a reload,
    so the fresh import can capture again under the same name."""
    handle = _REGISTRY.get(name)
    if handle is None:
        return
    set_enabled(mcp, name, False)
    del _REGISTRY[name]
