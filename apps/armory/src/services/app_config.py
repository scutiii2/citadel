"""Loaders for this server's JSON config files under configs/, split one file per concern.
Strings may use ``${VAR}`` (``$$`` for a literal ``$``), resolved per entry so one unset secret can't break unrelated config; failures raise KeyError (absent) or ValueError (unusable) naming file and key."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store



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


def _resolve_placeholder(name: str, *, where: str, config_path: Path) -> str:
    if name == "INTERNAL_API_TOKEN":
        raise ValueError("Legacy INTERNAL_API_TOKEN placeholder is unsupported; use service auth or an upstream-specific token")
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


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}.")
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as error:
        raise ValueError(f"Config file {path} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a JSON object at the top level")
    return data


def load_config(config_path: Path) -> dict[str, Any]:
    """Read and parse one config file, raising on anything unusable.
    Returns the document as written, ``${VAR}`` placeholders included; resolve with ``resolve_section``."""
    return _read_object(config_path)


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

EMAIL_TABLE = "email"
EMAIL_KEY = "smtp"
EMAIL_FIELDS = ("smtp_server", "smtp_port", "security", "from", "password", "to", "allowed_recipient_domains")


def email_document(config_path: Path) -> dict[str, Any] | None:
    """The stored SMTP document, or None when the administrator has not set email up."""
    document = settings_store.read_all(config_path, EMAIL_TABLE).get(EMAIL_KEY)
    return document if isinstance(document, dict) else None


def load_email_config(config_path: Path) -> EmailConfig:
    """Build an EmailConfig from the SMTP settings stored in the settings database at ``config_path``; ``from`` is exposed as ``from_address``.
    Optional keys: ``password`` (unauthenticated relays), ``security`` (implied by port), ``allowed_recipient_domains`` (absent is stricter), ``to``."""
    section = email_document(config_path)
    if section is None:
        raise FileNotFoundError(f"Email is not set up in {config_path}.")
    return _email_config(section, config_path)


def save_email_settings(config_path: Path, changes: dict[str, Any]) -> dict[str, Any]:
    """Merge ``changes`` into the stored document (a None value removes a key), check the result as a whole, and save it.
    Raises KeyError or ValueError, and saves nothing, when the result is not a usable email setup."""
    unknown = set(changes) - set(EMAIL_FIELDS)
    if unknown:
        raise ValueError(f"Unknown email setting: {', '.join(sorted(unknown))}.")
    document = {**(email_document(config_path) or {})}
    for key, value in changes.items():
        if value is None:
            document.pop(key, None)
        else:
            document[key] = value
    _email_config(document, config_path)
    settings_store.put(config_path, EMAIL_TABLE, EMAIL_KEY, document)
    return document


def _email_config(section: dict[str, Any], config_path: Path) -> EmailConfig:
    def required(key: str) -> Any:
        if key not in section or section[key] in ("", None):
            raise KeyError(f"Email settings are missing '{key}'")
        return section[key]

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

    try:
        port = int(required("smtp_port"))
    except (TypeError, ValueError):
        raise ValueError("Email settings: 'smtp_port' must be a whole number.") from None
    inferred = "ssl" if port == IMPLICIT_TLS_PORT else "starttls"
    security = str(section.get("security", inferred)).strip().lower()
    if security not in SUPPORTED_EMAIL_SECURITY:
        # No permissive fallback on a typo: downgrading "tls" to plaintext or unverified would silently send the password in the clear.
        raise ValueError(
            f"Email settings: 'security' is {security!r}, "
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
    )


# --- capabilities ---
# Which built-in capabilities (src/capabilities/<name>/) are enabled: read at startup by run.py, written by capability_routes.py's PATCH, which also applies the change live.


def load_capabilities_config(config_path: Path) -> dict[str, dict[str, Any]]:
    """The capability entries in the settings store: which capabilities are enabled.
    An empty store gives {}: nothing is switched on until an administrator does it."""
    return settings_store.read_all(config_path, "capabilities")


def capability_enabled(config: dict[str, dict[str, Any]], name: str) -> bool:
    """True unless `name` is present in `config` with `"enabled": false`.
    Only called for a name that has an entry; a capability with no entry is never loaded."""
    entry = config.get(name, {})
    if not isinstance(entry, dict):
        return True
    return bool(entry.get("enabled", True))


def save_capabilities_config(config_path: Path, name: str, enabled: bool) -> None:
    """Persist one capability's enabled state, leaving other entries untouched.
    A capability with no entry stays offline: an administrator turns each one on, on the deployed machine."""
    entry = settings_store.read_all(config_path, "capabilities").get(name, {})
    settings_store.put(config_path, "capabilities", name, {**entry, "enabled": enabled})


RENAMED_CAPABILITIES = {"video": "media"}


def migrate_renamed_capabilities(config_path: Path) -> None:
    """Move the entry of a renamed capability to its new id, so its on/off state survives.
    An entry already under the new id wins. Writes only when something moved."""
    data = settings_store.read_all(config_path, "capabilities")
    for old, new in RENAMED_CAPABILITIES.items():
        if old in data:
            if new not in data:
                settings_store.put(config_path, "capabilities", new, data[old])
            settings_store.delete(config_path, "capabilities", old)
