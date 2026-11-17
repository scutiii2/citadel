"""Server-wide settings; plain on purpose, swap for pydantic-settings if the tunables grow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from src.citadel_auth import apply_root_env, cache_dir, data_dir
from src.environment_settings import overlay

_PROJECT = Path(__file__).resolve().parent.parent
apply_root_env(_PROJECT)  # the Citadel root .env overrides this service's .env
# Runtime data and cache live under the Citadel root: .data/armory and .cache/armory (see citadel_auth.paths).
DATA = data_dir(_PROJECT)
CACHE = cache_dir(_PROJECT)



def _env(name: str, default: str) -> str:
    """os.getenv, but an empty value counts as unset.
    A blank line like ``MCP_LOG_DIR=`` would otherwise override a default with Path("")."""
    value = os.getenv(name)
    return value if value else default


@dataclass(frozen=True)
class Settings:
    # Loopback by default: this server has no auth, so anything reaching the port can call every tool.
    # Set MCP_HOST to expose it only behind a reverse proxy, VPN or firewall that authenticates.
    host: str = _env("MCP_HOST", "127.0.0.1")
    port: int = int(_env("MCP_PORT", "29600"))
    # Where logging_setup.configure_logging() writes server.log and errors.report() writes per-reference files.
    # Relative to CWD like the paths above.
    log_dir: Path = Path(_env("MCP_LOG_DIR", str(DATA / "logs")))
    # Where POST /upload (upload_routes.py) writes files dropped into a command-form modal.
    # Relative to CWD like the paths above.
    uploads_dir: Path = Path(_env("MCP_UPLOADS_DIR", str(DATA / "uploads")))
    pdf_merger_store_dir: Path = Path(_env("MCP_PDF_MERGER_STORE_DIR", str(DATA / "pdf_merger" / "store")))
    pdf_merger_public_base_url: str = _env("MCP_PDF_MERGER_PUBLIC_BASE_URL", "")
    pdf_merger_signing_key: str = _env("PDF_MERGER_SIGNING_KEY", "")
    # Where capability-owned job watchers keep their state
    # records. Relative to CWD, like uploads_dir.
    watchers_dir: Path = Path(_env("MCP_WATCHERS_DIR", str(DATA / "watchers")))
    email_audit_path: Path = Path(_env("MCP_EMAIL_AUDIT_PATH", str(DATA / "email" / "audit.db")))
    # Per-user memory notes (capabilities/memory). Runtime state: gitignored.
    memory_db_path: Path = Path(_env("MCP_MEMORY_DB_PATH", str(DATA / "memory" / "memory.db")))
    # Per-user learned skills (capabilities/skills). Runtime state: gitignored.
    skills_db_path: Path = Path(_env("MCP_SKILLS_DB_PATH", str(DATA / "skills" / "skills.db")))
    # Capability toggles, extensions and ticket settings that admin pages change (citadel_auth/settings_store.py).
    settings_db_path: Path = Path(_env("MCP_SETTINGS_DB_PATH", str(DATA / "settings.db")))
    # Support tickets (capabilities/tickets/utils/service.py): SQLite file and the optional Laya MCP address (http://host:29611/mcp).
    # Blank LAYA_URL skips Laya; tickets still work.
    tickets_db_path: Path = Path(_env("MCP_TICKETS_DB_PATH", str(DATA / "tickets" / "tickets.db")))
    laya_url: str = _env("LAYA_URL", "")
    # db_gateway, where portcullis keeps per-account notes; the notes capability reads those shared with agents.
    # The instance must list the connection; requests carry Armory service assertions.
    db_gateway_url: str = _env("DB_GATEWAY_URL", "http://127.0.0.1:29602")
    db_gateway_instance: str = _env("DB_GATEWAY_INSTANCE", "mcp_server")
    db_gateway_connection: str = _env("DB_GATEWAY_CONNECTION", "data")
    # Obsidian Local REST API. Never include the address or credential in settings repr.
    obsidian_base_url: str = field(default=_env("OBSIDIAN_BASE_URL", "https://127.0.0.1:27124"), repr=False)
    obsidian_api_key: str = field(default=_env("OBSIDIAN_API_KEY", ""), repr=False)
    obsidian_timeout: float = float(_env("OBSIDIAN_TIMEOUT", "5"))
    obsidian_verify_tls: bool = _env("OBSIDIAN_VERIFY_TLS", "true").lower() != "false"
    obsidian_allow_write: bool = _env("OBSIDIAN_ALLOW_WRITE", "false").lower() == "true"
    obsidian_vault_path: str = _env("OBSIDIAN_VAULT_PATH", "")
    obsidian_index_path: Path = Path(_env("OBSIDIAN_INDEX_PATH", str(CACHE / "obsidian" / "index.db")))
    obsidian_ollama_url: str = _env("OBSIDIAN_OLLAMA_URL", "http://127.0.0.1:11434")
    obsidian_embed_model: str = _env("OBSIDIAN_EMBED_MODEL", "nomic-embed-text")
    obsidian_refresh_seconds: float = float(_env("OBSIDIAN_REFRESH_SECONDS", "60"))
    # Stronghold keeps the brain connections; Armory asks it which one an account may use.
    stronghold_url: str = _env("STRONGHOLD_URL", "http://127.0.0.1:29650")
    # Tavily API key for the web_research capability. Blank until set in .env;
    # the tools then fail with a message naming the variable.
    tavily_api_key: str = _env("TAVILY_API_KEY", "")
    # Firecrawl key and optional self-hosted address for the firecrawl capability.
    # Blank key: the tools fail naming the variable (a self-hosted URL may run keyless).
    firecrawl_api_key: str = _env("FIRECRAWL_API_KEY", "")
    firecrawl_api_url: str = _env("FIRECRAWL_API_URL", "")

    # Video downloads stay on armory's listener; only the public origin is configurable.
    media_store_dir: Path = Path(_env("MCP_MEDIA_STORE_DIR", str(CACHE / "media_downloader" / "store")))
    media_log_dir: Path = Path(_env("MCP_MEDIA_LOG_DIR", str(DATA / "media_downloader" / "logs")))
    media_public_base_url: str = _env("MCP_MEDIA_PUBLIC_BASE_URL", "")
    media_signing_key: str = _env("MCP_MEDIA_SIGNING_KEY", "")

    # Folders the read-only capabilities look at, relative to apps/armory/.
    # usage_report: ai_agent's usage log. vault: the Obsidian vault. repo_reader: the folder holding project repos.
    usage_dir: Path = Path(_env("MCP_USAGE_DIR", str(data_dir(_PROJECT.parent / "legion") / "usage")))
    vault_dir: Path = Path(_env("MCP_VAULT_DIR", "../../../../Brain"))
    workspace_dir: Path = Path(_env("MCP_WORKSPACE_DIR", "../../../.."))



# .env and the defaults give the first value; what an administrator saved (environment_settings.py) wins.
settings = overlay(Settings(), Settings().settings_db_path)
