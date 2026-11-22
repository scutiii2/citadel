"""portcullis settings: configs/config_app.json, overridable by env vars."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.citadel_auth import apply_root_env, data_dir
from src.utils.config_loader import load_json_config
from src.utils.env_file import ensure_env_file

PROJECT_DIR = Path(__file__).resolve().parent.parent
apply_root_env(PROJECT_DIR)  # the Citadel root .env overrides this service's .env
CONFIGS_DIR = PROJECT_DIR / "configs"
ENV_PATH = PROJECT_DIR / ".env"
# Pre-.env layout: one secret_*.env file per concern. Read once to build .env.
LEGACY_SECRETS_DIR = PROJECT_DIR / "secrets"



@dataclass(frozen=True)
class SecuritySettings:
    """config_app.json's "security" block (port of chat_app's
    config_security_*.json). Every field has a safe default, so a config
    file without the block still gets login rate limiting and headers."""

    # Login rate limiting: after `max_attempts` failed logins within
    # `window_seconds`, login is refused (429) until `lockout_seconds` after
    # the last failure. scope: "ip", "account" or "both" (either can trip it).
    rate_limit_enabled: bool = True
    max_attempts: int = 5
    window_seconds: int = 900
    lockout_seconds: int = 900
    rate_limit_scope: str = "both"
    # Requests from these addresses may name the real client in
    # X-Forwarded-For (Vite's dev/preview proxy runs on loopback). Anything
    # else is taken at its socket address, so the header can't be spoofed.
    trusted_proxies: tuple[str, ...] = ("127.0.0.1", "::1")
    # Networks (CIDR or single address). Deny wins; a non-empty allow list
    # refuses everything not on it. Checked on every request (403).
    ip_allow_list: tuple[str, ...] = ()
    ip_deny_list: tuple[str, ...] = ()
    outside_ip_allow_list: tuple[str, ...] = ()
    outside_ip_deny_list: tuple[str, ...] = ()
    # nosniff / frame / referrer / CSP headers on every response.
    security_headers: bool = True
    # >0 adds Strict-Transport-Security; only once served over HTTPS.
    hsts_max_age: int = 0
    # Device fingerprinting: a login from a device (these request signals)
    # the account never used is written to the activity log.
    fingerprint_enabled: bool = True
    fingerprint_signals: tuple[str, ...] = ("user_agent", "accept_language", "ip_subnet")

    @classmethod
    def from_config(cls, raw: dict) -> SecuritySettings:
        rate = raw.get("rate_limit", {})
        ip_filter = raw.get("ip_filter", {})
        outside_ip_filter = raw.get("outside_ip_filter", {})
        headers = raw.get("headers", {})
        fingerprint = raw.get("fingerprint", {})
        scope = rate.get("scope", "both")
        if scope not in ("ip", "account", "both"):
            raise ValueError(f'security.rate_limit.scope must be "ip", "account" or "both", not {scope!r}')
        signals = tuple(fingerprint.get("signals", ("user_agent", "accept_language", "ip_subnet")))
        unknown = [s for s in signals if s not in ("user_agent", "accept_language", "ip_subnet")]
        if unknown or not signals:
            raise ValueError(
                'security.fingerprint.signals must be a non-empty list of "user_agent", "accept_language", "ip_subnet"'
            )
        return cls(
            rate_limit_enabled=bool(rate.get("enabled", True)),
            max_attempts=int(rate.get("max_attempts", 5)),
            window_seconds=int(rate.get("window_seconds", 900)),
            lockout_seconds=int(rate.get("lockout_seconds", 900)),
            rate_limit_scope=scope,
            trusted_proxies=tuple(raw.get("trusted_proxies", ("127.0.0.1", "::1"))),
            ip_allow_list=tuple(ip_filter.get("allow_list", ())),
            ip_deny_list=tuple(ip_filter.get("deny_list", ())),
            outside_ip_allow_list=tuple(outside_ip_filter.get("allow_list", ())),
            outside_ip_deny_list=tuple(outside_ip_filter.get("deny_list", ())),
            security_headers=bool(headers.get("enabled", True)),
            hsts_max_age=int(headers.get("hsts_max_age", 0)),
            fingerprint_enabled=bool(fingerprint.get("enabled", True)),
            fingerprint_signals=signals,
        )


@dataclass(frozen=True)
class BackupSettings:
    """config_app.json's "backup" block: a copy of the database every
    `every_hours` hours, the newest `keep` of them kept (in `backups/` beside the database)."""

    enabled: bool = True
    keep: int = 14
    every_hours: int = 24

    @classmethod
    def from_config(cls, raw: dict) -> BackupSettings:
        keep = int(raw.get("keep", 14))
        every_hours = int(raw.get("every_hours", 24))
        if keep < 1:
            raise ValueError("backup.keep must be at least 1")
        if every_hours < 1:
            raise ValueError("backup.every_hours must be at least 1")
        return cls(enabled=bool(raw.get("enabled", True)), keep=keep, every_hours=every_hours)


@dataclass(frozen=True)
class DbGatewaySettings:
    """config_app.json's "db_gateway" block: where new document data is stored
    (the db_gateway project), and which of its instances and connections to use."""

    instance: str = "ember"
    connection: str = "data"

    @classmethod
    def from_config(cls, raw: dict) -> DbGatewaySettings:
        instance = str(raw.get("instance") or cls.instance)
        connection = str(raw.get("connection") or cls.connection)
        return cls(instance=instance, connection=connection)


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_path: Path
    session_cookie_name: str
    session_hours: int
    cookie_secure: bool
    env_path: Path
    treasury_url: str = "http://127.0.0.1:29602"
    advertise_url: str | None = None
    default_role: str = "Member"
    # Origins of the Ember Windows app (Tauri). They may call the API with a bearer token; cookies are never allowed cross-origin.
    desktop_origins: tuple[str, ...] = ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost")
    # False: an account works without verifying its email, and registration
    # sends no code. Verifying stays available (resend, the verify page).
    require_email_verification: bool = True
    agents_registry_path: Path = data_dir(PROJECT_DIR.parent / "legion") / "agent_registry.json"
    # ai_agent's GET /registry, for an ai_agent in another directory or on
    # another machine. Wins over agents_registry_path when set.
    agents_registry_url: str | None = None
    # Stronghold (product logic): reached only from here, never by the browser.
    security: SecuritySettings = field(default_factory=SecuritySettings)
    backup: BackupSettings = field(default_factory=BackupSettings)
    db_gateway: DbGatewaySettings = field(default_factory=DbGatewaySettings)
    # Where these settings came from (the Config issues page re-reads it).
    config_path: Path = CONFIGS_DIR / "config_app.json"

    @property
    def backup_dir(self) -> Path:
        return self.database_path.parent / "backups"

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"


def load_settings() -> Settings:
    """Reads config_app.json and makes
    sure .env exists (built from the old secrets/ files, else .env.example).
    EMBER_API_HOST / EMBER_API_PORT win over the file, so a launcher or
    container can pick the port."""
    raw = load_json_config(CONFIGS_DIR / "config_app.json")
    ensure_env_file(ENV_PATH, ENV_PATH.with_name(".env.example"), LEGACY_SECRETS_DIR)
    database_path = _project_path(raw["database_path"]) if raw.get("database_path") else data_dir(PROJECT_DIR) / "ember_api.db"
    # The policy settings an administrator edits (session length, rate limit, backups...) are not in the file.
    from src.services import app_policy  # here, not at the top: app_policy imports this module

    raw = app_policy.overlay(raw, database_path.parent / "settings.db")
    registry_path = raw.get("agents_registry_path") or data_dir(PROJECT_DIR.parent / "legion") / "agent_registry.json"
    return Settings(
        host=os.getenv("EMBER_API_HOST") or raw.get("host", "127.0.0.1"),
        port=int(os.getenv("EMBER_API_PORT") or raw.get("port", 29601)),
        database_path=database_path,
        session_cookie_name=raw.get("session_cookie_name", "ember_session"),
        session_hours=int(raw.get("session_hours", 12)),
        cookie_secure=bool(raw.get("cookie_secure", False)),
        env_path=ENV_PATH,
        treasury_url=os.getenv("TREASURY_URL") or raw.get("treasury_url") or "http://127.0.0.1:29602",
        advertise_url=raw.get("advertise_url") or None,
        default_role=raw.get("default_role") or "Member",
        desktop_origins=tuple(raw.get("desktop_origins", ("tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"))),
        require_email_verification=bool(raw.get("require_email_verification", True)),
        agents_registry_path=_project_path(registry_path),
        agents_registry_url=raw.get("agents_registry_url") or None,
        security=SecuritySettings.from_config(raw.get("security", {})),
        backup=BackupSettings.from_config(raw.get("backup", {})),
        db_gateway=DbGatewaySettings.from_config(raw.get("db_gateway", {})),
        config_path=CONFIGS_DIR / "config_app.json",
    )


def _project_path(value: str) -> Path:
    """Relative config paths are relative to the portcullis folder."""
    path = Path(value)
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()
