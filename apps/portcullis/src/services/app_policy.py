"""Portcullis's policy settings, kept in `settings.db` beside its database (table `app_config`).

Session length, the role a new account gets, email verification, login rate limiting, the IP filter, security headers,
device fingerprinting and database backups. An administrator edits them on the Workspace settings page of Portcullis
Admin; they are not in `configs/config_app.json`. A stored value wins over the built-in default. Portcullis reads them
once when it starts, so a change is used from the next start. Where Portcullis listens, its cookie, the addresses of
the other services and the trusted proxies stay in the tracked file: they describe the deployment.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store
from src.config import BackupSettings, SecuritySettings

TABLE = "app_config"
SECURITY_PARTS = ("rate_limit", "ip_filter", "outside_ip_filter", "headers", "fingerprint")
KEYS = ("session_hours", "default_role", "require_email_verification", *SECURITY_PARTS, "backup")
SIGNALS = ("user_agent", "accept_language", "ip_subnet")


class PolicyError(ValueError):
    """A change is refused; the message names the setting and is safe to show."""


def stored(path: Path) -> dict[str, Any]:
    return {key: value for key, value in settings_store.read_all(path, TABLE).items() if key in KEYS}


def overlay(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    """`raw` (the parsed file) with every stored policy value on top."""
    merged = dict(raw)
    security = dict(raw.get("security") or {})
    for key, value in stored(path).items():
        if key in SECURITY_PARTS:
            security[key] = value
        else:
            merged[key] = value
    merged["security"] = security
    return merged


def view(settings: Any, path: Path) -> dict[str, Any]:
    """The values that apply from the next start: the ones in use, with what was saved here on top."""
    in_use = _in_use(settings)
    saved = stored(path)
    for key, value in saved.items():
        in_use[key] = {**in_use[key], **value} if isinstance(value, dict) else value
    return {**in_use, "stored": sorted(saved)}


def _in_use(settings: Any) -> dict[str, Any]:
    security, backup = settings.security, settings.backup
    return {
        "session_hours": settings.session_hours,
        "default_role": settings.default_role,
        "require_email_verification": settings.require_email_verification,
        "rate_limit": {"enabled": security.rate_limit_enabled, "scope": security.rate_limit_scope,
                       "max_attempts": security.max_attempts, "window_seconds": security.window_seconds,
                       "lockout_seconds": security.lockout_seconds},
        "ip_filter": {"allow_list": list(security.ip_allow_list), "deny_list": list(security.ip_deny_list)},
        "outside_ip_filter": {"allow_list": list(security.outside_ip_allow_list),
                              "deny_list": list(security.outside_ip_deny_list)},
        "headers": {"enabled": security.security_headers, "hsts_max_age": security.hsts_max_age},
        "fingerprint": {"enabled": security.fingerprint_enabled, "signals": list(security.fingerprint_signals)},
        "backup": {"enabled": backup.enabled, "keep": backup.keep, "every_hours": backup.every_hours},
    }


def _whole(value: Any, minimum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PolicyError(f"{label} must be a whole number, {minimum} or more.")
    return value


def _flag(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyError(f"{label} must be on or off.")
    return value


def _networks(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PolicyError(f"{label} must be a list of addresses.")
    for item in value:
        try:
            ipaddress.ip_network(item.strip(), strict=False)
        except ValueError:
            raise PolicyError(f"{label}: {item!r} is not an address or network.") from None
    return [item.strip() for item in value]


def _checked(key: str, value: Any, current: dict[str, Any]) -> Any:
    """One setting as it is stored, or PolicyError. A group is merged into the current group first."""
    if key == "session_hours":
        return _whole(value, 1, "Session length")
    if key == "default_role":
        if not isinstance(value, str) or not value.strip():
            raise PolicyError("The role of a new account must be a name.")
        return value.strip()
    if key == "require_email_verification":
        return _flag(value, "Email verification")
    if not isinstance(value, dict) or not value:
        raise PolicyError(f"{key} must be an object with at least one value.")
    group = {**current[key], **value}
    unknown = set(group) - set(current[key])
    if unknown:
        raise PolicyError(f"Unknown {key} setting: {', '.join(sorted(unknown))}.")
    if key == "rate_limit":
        _flag(group["enabled"], "Rate limiting")
        if group["scope"] not in ("ip", "account", "both"):
            raise PolicyError('Rate limit scope must be "ip", "account" or "both".')
        for name in ("max_attempts", "window_seconds", "lockout_seconds"):
            _whole(group[name], 1, f"Rate limit {name}")
    elif key == "ip_filter":
        group = {"allow_list": _networks(group["allow_list"], "Allow list"), "deny_list": _networks(group["deny_list"], "Deny list")}
    elif key == "outside_ip_filter":
        group = {"allow_list": _networks(group["allow_list"], "Outside allow list"),
                 "deny_list": _networks(group["deny_list"], "Outside deny list")}
    elif key == "headers":
        _flag(group["enabled"], "Security headers")
        _whole(group["hsts_max_age"], 0, "HSTS max age")
    elif key == "fingerprint":
        _flag(group["enabled"], "Device fingerprinting")
        signals = group["signals"]
        if not isinstance(signals, list) or not signals or any(item not in SIGNALS for item in signals):
            raise PolicyError(f"Fingerprint signals must be a non-empty list of {', '.join(SIGNALS)}.")
    elif key == "backup":
        _flag(group["enabled"], "Backups")
        _whole(group["keep"], 1, "Backups to keep")
        _whole(group["every_hours"], 1, "Hours between backups")
    return group


def update(path: Path, settings: Any, changes: Any) -> list[str]:
    """Save `{key: value | None}` (a group is merged into the current one; None goes back to the default).
    Nothing is saved if one change is refused. Returns the changed keys; they are used from the next start."""
    if not isinstance(changes, dict) or not changes:
        raise PolicyError("Send at least one setting to change.")
    unknown = set(changes) - set(KEYS)
    if unknown:
        raise PolicyError(f"Unknown setting: {', '.join(sorted(unknown))}.")
    current = view(settings, path)
    checked = {key: (None if value is None else _checked(key, value, current)) for key, value in changes.items()}
    # The same builders Portcullis starts with must accept the result.
    try:
        SecuritySettings.from_config({part: checked.get(part) or current[part] for part in SECURITY_PARTS})
        BackupSettings.from_config(checked.get("backup") or current["backup"])
    except (ValueError, TypeError, AttributeError) as error:
        raise PolicyError(str(error)) from error
    for key, value in checked.items():
        if value is None:
            settings_store.delete(path, TABLE, key)
        else:
            settings_store.put(path, TABLE, key, value)
    return sorted(checked)
