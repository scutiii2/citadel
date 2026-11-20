"""Load and validate the `servers` table of Legion's settings database into typed
ServerConfig objects.

Mirrors the shape of mcp_server/src/infra/app_config.py's ExtensionConfig,
generalized with an optional `auth` block - every configured server here
(including the main mcp_server itself) is symmetric, unlike mcp_server's
extensions.py, which distinguishes "our own tools" from "proxied tools"
because it is itself a server with tools of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store, resolved


class ConfigError(ValueError):
    """Raised for a malformed server entry."""


@dataclass(frozen=True)
class AuthConfig:
    type: str  # "none" | "header" | "bearer_env"
    env_var: str | None = None
    header_name: str | None = None
    header_value: str | None = None


@dataclass(frozen=True)
class OriginRef:
    """One address of an outside service: an id from Treasury's catalog and an optional token of its own."""

    origin_id: str
    header_value: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ServerConfig:
    id: str
    label: str
    description: str
    transport: str  # "stdio" | "http"
    url: str | Callable[[], str] | None = None
    command: str | None = None
    args: list[str] | None = None
    auth: AuthConfig | None = None
    service_id: str | None = None
    path: str = "/mcp"
    origins: tuple[OriginRef, ...] = ()


_VALID_TRANSPORTS = {"stdio", "http"}
_VALID_AUTH_TYPES = {"none", "header", "bearer_env"}


def _build_auth(server_id: str, raw: dict[str, Any] | None) -> AuthConfig | None:
    if raw is None:
        return None
    auth_type = raw.get("type")
    if auth_type not in _VALID_AUTH_TYPES:
        raise ConfigError(f"{server_id!r}: auth.type must be one of {sorted(_VALID_AUTH_TYPES)}, got {auth_type!r}")
    if auth_type == "header" and not (raw.get("header_name") and raw.get("header_value")):
        raise ConfigError(f"{server_id!r}: auth.type 'header' requires header_name and header_value")
    if auth_type == "bearer_env" and not raw.get("env_var"):
        raise ConfigError(f"{server_id!r}: auth.type 'bearer_env' requires env_var")
    return AuthConfig(
        type=auth_type,
        env_var=raw.get("env_var"),
        header_name=raw.get("header_name"),
        header_value=raw.get("header_value"),
    )


def _build_origin(server_id: str, raw: Any) -> OriginRef:
    origin_id = raw.get("origin_id") if isinstance(raw, dict) else None
    if not isinstance(origin_id, str) or not origin_id:
        raise ConfigError(f"{server_id!r}: every origin needs an 'origin_id'")
    token = raw.get("header_value")
    return OriginRef(origin_id, token if isinstance(token, str) and token else None)


def _build_server(server_id: str, raw: dict[str, Any]) -> ServerConfig:
    transport = raw.get("transport")
    if transport not in _VALID_TRANSPORTS:
        raise ConfigError(f"{server_id!r}: transport must be one of {sorted(_VALID_TRANSPORTS)}, got {transport!r}")

    label = raw.get("label")
    if not label:
        raise ConfigError(f"{server_id!r}: 'label' is required")
    description = raw.get("description", "")

    service_id = raw.get("service_id")
    raw_origins = raw.get("origins")
    has_origin_fields = "service_id" in raw or "origins" in raw
    origins: tuple[OriginRef, ...] = ()
    path = "/mcp"
    if transport == "http":
        if raw.get("command"):
            raise ConfigError(f"{server_id!r}: transport 'http' must not set 'command'")
        command, args = None, None
        if has_origin_fields:
            if "url" in raw:
                raise ConfigError(f"{server_id!r}: use either 'url' or 'origins', not both")
            if not isinstance(service_id, str) or not service_id:
                raise ConfigError(f"{server_id!r}: 'origins' requires 'service_id'")
            if not isinstance(raw_origins, list) or not raw_origins:
                raise ConfigError(f"{server_id!r}: 'service_id' requires at least one origin")
            origins = tuple(_build_origin(server_id, item) for item in raw_origins)
            if len({origin.origin_id for origin in origins}) != len(origins):
                raise ConfigError(f"{server_id!r}: an origin is listed twice")
            path = raw.get("path", "/mcp")
            if not isinstance(path, str) or not path.startswith("/") or any(char in path for char in "?# \\"):
                raise ConfigError(f"{server_id!r}: 'path' must start with / and hold no query or space")
            url = None
        else:
            url = raw.get("url")
            if not url:
                raise ConfigError(f"{server_id!r}: transport 'http' requires 'url'")
    else:
        command = raw.get("command")
        if not command:
            raise ConfigError(f"{server_id!r}: transport 'stdio' requires 'command'")
        if raw.get("url") or has_origin_fields:
            raise ConfigError(f"{server_id!r}: transport 'stdio' must not set 'url' or 'origins'")
        url = None
        args = raw.get("args", [])

    return ServerConfig(
        id=server_id,
        label=label,
        description=description,
        transport=transport,
        url=url,
        command=command,
        args=args,
        auth=_build_auth(server_id, raw.get("auth")),
        service_id=service_id if origins else None,
        path=path,
        origins=origins,
    )


def validate_server(server_id: str, raw: dict[str, Any]) -> ServerConfig:
    """One entry checked as a server; raises ConfigError."""
    return _build_server(server_id, raw)


def load_servers_config(
    path: Path,
    url_overrides: dict[str, str | Callable[[], str]] | None = None,
    builtins: dict[str, dict] | None = None,
) -> dict[str, ServerConfig]:
    """Load and validate every server in the settings database at `path`.

    Raises ConfigError for any entry missing a required field, using an
    unknown transport/auth type, or mixing fields from the wrong
    transport (e.g. an http entry with 'command' set). The whole file is
    validated eagerly on load - a bad entry anywhere fails loudly at
    startup rather than surfacing later as a confusing connect failure.

    `url_overrides` (server_id -> url) replaces an http entry's configured
    url after loading - used by mcp_upstream.py to let --mcp-url/
    the catalog default repoint the "main" upstream server without editing
    changing the stored entry. Ignored for a stdio entry or an unknown server_id.
    """
    raw_data = settings_store.read_all(path, "servers")
    for server_id, entry in (builtins or {}).items():
        raw_data.setdefault(server_id, entry)
    # The catalog supplies Armory on fresh installs or when main has no saved URL.
    if url_overrides and "main" in url_overrides:
        main = raw_data.get("main", {"label": "Armory", "transport": "http"})
        if main.get("transport") == "http" and not main.get("url") and "origins" not in main:
            raw_data["main"] = {**main, "url": resolved(url_overrides["main"])}
    servers = {server_id: _build_server(server_id, raw) for server_id, raw in raw_data.items()}
    for server_id, url in (url_overrides or {}).items():
        config = servers.get(server_id)
        if config is not None and config.transport == "http" and not config.origins:
            servers[server_id] = replace(config, url=url)
    return servers
