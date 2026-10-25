"""Loaders for this server's JSON config files under configs/, split one file per concern.
Strings may use ``${VAR}`` (``$$`` for a literal ``$``), resolved per entry so one unset secret can't break unrelated config; failures raise KeyError (absent) or ValueError (unusable) naming file and key."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit



# ${NAME} (a normal env-var identifier) is expanded; a "$" not followed by "{" is left alone.
# "$$" escapes a literal "$" (as in docker-compose), so "$${NAME}" survives as "${NAME}".
_ENV_PLACEHOLDER = re.compile(r"\$\$|\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class EmailConfig:
    smtp_server: str
    smtp_port: int
    from_address: str
    # The standing recipient list; empty is valid for deployments that only mail one-time codes to
    # caller-named addresses (see `allowed_recipient_domains`). `send_email` refuses an empty final list.
    to: list[str] = field(default_factory=list)
    # Empty means connect and send without authenticating: LAN relays and local MTAs authorize by source address,
    # and a consumer provider rejects the mail, which is correct for a missing password.
    password: str = ""
    # How the connection is protected: "starttls" | "ssl" | "none".
    # Defaults to STARTTLS; `load_email_config` infers a better default from the port.
    security: str = "starttls"
    # Domains a caller may name any address at; currently unused (its OTP consumer was removed), kept as infrastructure.
    # Empty means "no domains", never "any domain", so an absent key is the strict case.
    allowed_recipient_domains: list[str] = field(default_factory=list)
    # Optional MS Teams incoming-webhook URL for state-transition alerts (none currently).
    # Empty means Teams alerts are off; an empty string is never POSTed to.
    teams_webhook_url: str = ""


@dataclass(frozen=True)
class ExtensionConfig:
    """One other MCP server this server connects to as a client and re-exposes as namespaced tools (see ``services/extensions.py``).
    Transport is "stdio" (spawned local subprocess via ``command``/``args``) or "http" (``url`` of a running server), chosen in ``_build_extension``."""

    id: str
    label: str
    description: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    transport: str = "stdio"
    url: str | None = None
    # http transport only: extra headers sent on every request to the upstream (e.g. {"X-Internal-Token": "${INTERNAL_API_TOKEN}"}).
    # Values are resolved from the environment at load time, so they are secrets: never persisted or reported.
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    # Opt-in: send the asking user's username/email upstream as ``_meta.requester`` on each proxied call.
    # Off by default so an extension never receives identity data it did not ask for.
    forward_requester: bool = False
    # The extension's own web app, if any (an http(s) address the browser can reach, not necessarily the MCP url).
    # ember's Extensions page links to it; nothing here requests it.
    web_url: str | None = None


def _web_url(entry: dict[str, Any], *, id_: str, config_path: Path) -> str | None:
    """The optional ``web_url`` of an entry: absent -> None, else a non-empty http(s) URL with a host.
    Anything else (``javascript:``, relative path) is rejected so it never reaches a browser as a link."""
    if "web_url" not in entry:
        return None
    value = entry["web_url"]
    problem = f"Config file {config_path}: '{id_}.web_url' must be an http:// or https:// address"
    if not isinstance(value, str):
        raise ValueError(problem)
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(problem)
    return value.strip()


def _resolve_placeholder(name: str, *, where: str, config_path: Path) -> str:
    value = os.environ.get(name)
    if value is None:
        raise KeyError(
            f"Config file {config_path} refers to ${{{name}}} at '{where}', but "
            f"{name} is not set in the environment. Add it to mcp_server/.env "
            f"(or however this deployment supplies secrets)."
        )
    if value == "":
        # Almost always "SMTP_PASSWORD=" left blank in .env, which fails later at SMTP login with a vague message.
        # Write "" directly in the config file if empty is intended.
        raise ValueError(
            f"Config file {config_path} refers to ${{{name}}} at '{where}', but "
            f"{name} is set to an empty string. Give it a value, or put a "
            f"literal \"\" in the config file if empty is intended."
        )
    return value


def resolve_section(value: Any, *, where: str, config_path: Path) -> Any:
    """Substitute ${VAR} inside every string of one subtree of the config, recursing through dicts and lists.
    ``where`` is the subtree's full dotted path ("hosts.desktop") for error messages; only values change, never keys."""
    if isinstance(value, dict):
        return {
            key: resolve_section(item, where=f"{where}.{key}" if where else str(key), config_path=config_path)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_section(item, where=f"{where}[{index}]", config_path=config_path)
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        def substitute(match: re.Match[str]) -> str:
            if match.group(0) == "$$":
                return "$"
            return _resolve_placeholder(match.group(1), where=where, config_path=config_path)

        return _ENV_PLACEHOLDER.sub(substitute, value)
    return value


def load_config(config_path: Path) -> dict[str, Any]:
    """Read and parse one config file, raising on anything unusable.
    Returns the document as written, ``${VAR}`` placeholders included; resolve with ``resolve_section``."""
    example_path = config_path.with_name(config_path.name + ".example")
    if not config_path.exists() and example_path.exists():
        shutil.copyfile(example_path, config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Copy {config_path.name}.example "
            f"to {config_path.name} in the same folder and fill it in."
        )
    try:
        with config_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as error:
        raise ValueError(f"Config file {config_path} is not valid JSON: {error}") from error

    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_path} must contain a JSON object at the top level")
    return data


def _require(section: dict[str, Any], key: str, *, prefix: str, config_path: Path) -> Any:
    if key not in section:
        full_key = f"{prefix}.{key}" if prefix else key
        raise KeyError(f"Config file {config_path} is missing '{full_key}'")
    return section[key]


def normalize_recipient_domain(value: str) -> str:
    """One ``email.allowed_recipient_domains`` entry in comparison form; public so capabilities share one normalization.
    A leading ``@`` or ``.`` is stripped; nothing else is repaired, so a non-domain fails to match."""
    return value.strip().lower().lstrip("@.")


SUPPORTED_EMAIL_SECURITY = ("starttls", "ssl", "none")

# The IANA implicit-TLS submission port, used by mainstream providers, so `security` can be inferred from it.
IMPLICIT_TLS_PORT = 465

def load_email_config(config_path: Path) -> EmailConfig:
    """Parse config_email.json into an EmailConfig; ``from`` is read from JSON and exposed as ``from_address``.
    Optional keys: ``password`` (unauthenticated relays), ``security`` (implied by port), ``allowed_recipient_domains`` (absent is stricter), ``to``."""
    section = load_config(config_path)
    section = resolve_section(section, where="", config_path=config_path)

    def required(key: str) -> Any:
        return _require(section, key, prefix="", config_path=config_path)

    def as_string_list(value: Any) -> list[str]:
        # A bare string is the obvious way to write one recipient or domain; iterating it per character would be a nasty surprise.
        if isinstance(value, str):
            value = [value]
        return [str(item) for item in value]

    # Empty is allowed: `send_email` already refuses "No recipients" at send time, and a load-time failure
    # would forbid configs that send only to caller-named addresses.
    recipients = as_string_list(section.get("to", []))

    domains = [
        normalize_recipient_domain(entry)
        for entry in as_string_list(section.get("allowed_recipient_domains", []))
    ]
    # A blank entry (left by editing a JSON list) is dropped, not rejected: it can only fail to match
    # and would just appear in refusal messages.
    domains = [domain for domain in domains if domain]

    port = int(required("smtp_port"))
    inferred = "ssl" if port == IMPLICIT_TLS_PORT else "starttls"
    security = str(section.get("security", inferred)).strip().lower()
    if security not in SUPPORTED_EMAIL_SECURITY:
        # No permissive fallback on a typo: downgrading "tls" to plaintext or unverified would silently send the password in the clear.
        raise ValueError(
            f"Config file {config_path}: 'security' is {security!r}, "
            f"expected one of {', '.join(SUPPORTED_EMAIL_SECURITY)}."
        )

    return EmailConfig(
        smtp_server=str(required("smtp_server")),
        smtp_port=port,
        from_address=str(required("from")),
        to=recipients,
        password=str(section.get("password", "")),
        security=security,
        allowed_recipient_domains=domains,
        teams_webhook_url=str(section.get("teams_webhook_url", "")),
    )


def _extensions_section(config_path: Path) -> dict[str, Any]:
    """The raw extensions mapping, placeholders still unresolved -
    config_extensions.json's whole content."""
    return load_config(config_path)


def _build_extension(id_: str, entry: Any, *, config_path: Path) -> ExtensionConfig:
    """Resolve and validate one raw extension entry into an ExtensionConfig, one entry at a time so a bad sibling can't block it.
    Transport is inferred from ``command`` vs ``url``; both or neither is rejected."""
    if not isinstance(entry, dict):
        raise ValueError(f"Config file {config_path}: '{id_}' must be an object")

    entry = resolve_section(entry, where=id_, config_path=config_path)

    def required(key: str) -> Any:
        return _require(entry, key, prefix=id_, config_path=config_path)

    has_command = "command" in entry
    has_url = "url" in entry
    if has_command and has_url:
        raise ValueError(
            f"Config file {config_path}: '{id_}' has both 'command' and 'url' - "
            f"a stdio extension (spawned as a subprocess) uses 'command' and optionally "
            f"'args'; an http extension (already running elsewhere) uses 'url'. Remove one."
        )
    if not has_command and not has_url:
        raise ValueError(
            f"Config file {config_path}: '{id_}' needs either 'command' (to launch "
            f"a stdio extension) or 'url' (to connect to an already-running http extension)."
        )

    label = str(required("label"))
    description = str(entry.get("description", ""))

    headers = entry.get("headers", {})
    if "headers" in entry and not has_url:
        raise ValueError(
            f"Config file {config_path}: '{id_}.headers' only applies to an http extension "
            f"(one with 'url'). A stdio extension talks over stdin/stdout and sends no HTTP headers."
        )
    if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
        raise ValueError(f"Config file {config_path}: '{id_}.headers' must be an object of string values")

    forward_requester = entry.get("forward_requester", False)
    if not isinstance(forward_requester, bool):
        raise ValueError(f"Config file {config_path}: '{id_}.forward_requester' must be true or false")

    web_url = _web_url(entry, id_=id_, config_path=config_path)

    if has_url:
        url = str(required("url")).strip()
        if not url:
            raise ValueError(f"Config file {config_path}: '{id_}.url' must not be empty")
        return ExtensionConfig(
            id=id_, label=label, description=description, transport="http", url=url, headers=dict(headers),
            forward_requester=forward_requester, web_url=web_url,
        )

    args = entry.get("args", [])
    if not isinstance(args, list):
        raise ValueError(f"Config file {config_path}: '{id_}.args' must be a list")

    return ExtensionConfig(
        id=id_,
        label=label,
        description=description,
        transport="stdio",
        command=str(required("command")),
        args=[str(item) for item in args],
        forward_requester=forward_requester,
        web_url=web_url,
    )


def load_extensions_config(config_path: Path) -> dict[str, ExtensionConfig]:
    """Parse config_extensions.json into ExtensionConfigs keyed by id, once at startup.
    See ``_build_extension`` for why one broken entry doesn't stop the rest."""
    section = _extensions_section(config_path)
    return {id_: _build_extension(id_, entry, config_path=config_path) for id_, entry in section.items()}


def load_extension_config(config_path: Path, id_: str) -> ExtensionConfig:
    """One extension by id, listing the available ids if missing.
    Only the named entry is resolved, so a broken sibling can't block it."""
    section = _extensions_section(config_path)
    if id_ not in section:
        known = ", ".join(sorted(section)) or "none configured"
        raise KeyError(f"Unknown extension {id_!r}. Configured extensions: {known}.")

    return _build_extension(id_, section[id_], config_path=config_path)


def _write_config(config_path: Path, data: dict[str, Any]) -> None:
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def save_extension_config(config_path: Path, config: ExtensionConfig) -> None:
    """Insert or overwrite one entry in config_extensions.json, leaving every other entry untouched.
    Reads with ``load_config`` so other entries' ``${VAR}`` pass through unresolved; writes only the transport's fields, and never ``headers`` (resolved secrets; configure by hand)."""
    data = load_config(config_path)

    entry: dict[str, Any] = {"label": config.label, "description": config.description}
    if config.transport == "http":
        entry["url"] = config.url
    else:
        entry["command"] = config.command
        entry["args"] = config.args
    if config.web_url:
        entry["web_url"] = config.web_url
    data[config.id] = entry

    _write_config(config_path, data)


def delete_extension_config(config_path: Path, extension_id: str) -> None:
    """Remove one entry from config_extensions.json.
    Idempotent: removing an absent id is not an error."""
    data = load_config(config_path)
    data.pop(extension_id, None)
    _write_config(config_path, data)


# --- capabilities ---
# Which built-in capabilities (src/capabilities/<name>/) are enabled: read at startup by run.py, written by capability_routes.py's PATCH, which also applies the change live.


def load_capabilities_config(config_path: Path) -> dict[str, dict[str, Any]]:
    """Read config_capabilities.json: which capabilities are enabled.
    A missing file gives {} (all enabled), unlike other loaders, so deployments predating it keep working."""
    if not config_path.exists():
        return {}
    return load_config(config_path)


def capability_enabled(config: dict[str, dict[str, Any]], name: str) -> bool:
    """True unless `name` is present in `config` with `"enabled": false`.
    An unlisted capability is enabled; defaulting to disabled would make every capability vanish once the file exists."""
    entry = config.get(name, {})
    if not isinstance(entry, dict):
        return True
    return bool(entry.get("enabled", True))


def save_capabilities_config(config_path: Path, name: str, enabled: bool) -> None:
    """Persist one capability's enabled state, leaving other entries untouched; mirrors save_extension_config.
    A missing file is fine: this is the first writer of config_capabilities.json."""
    data = load_config(config_path) if config_path.exists() else {}
    data.setdefault(name, {})["enabled"] = enabled
    _write_config(config_path, data)


_SCANNER_MARKER = "_scanner"


def migrate_capabilities_config(config_path: Path, ids: list[str]) -> None:
    """Once, on the folder scanner's first run: write ``enabled: true`` for every capability without an entry, then set a marker.
    Afterwards a new folder with no entry stays offline until an admin enables it; does nothing once the marker exists."""
    data = load_config(config_path) if config_path.exists() else {}
    if _SCANNER_MARKER in data:
        return
    for capability_id in ids:
        data.setdefault(capability_id, {"enabled": True})
    data[_SCANNER_MARKER] = {"migrated": True}
    _write_config(config_path, data)


RENAMED_CAPABILITIES = {"video": "media"}


def migrate_renamed_capabilities(config_path: Path) -> None:
    """Move the entry of a renamed capability to its new id, so its on/off state survives.
    An entry already under the new id wins. Writes only when something moved."""
    if not config_path.exists():
        return
    data = load_config(config_path)
    moved = False
    for old, new in RENAMED_CAPABILITIES.items():
        if old in data:
            data.setdefault(new, data[old])
            del data[old]
            moved = True
    if moved:
        _write_config(config_path, data)
