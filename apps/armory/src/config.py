"""Server-wide settings.

Deliberately plain (no external settings library required) - swap for
pydantic-settings later if the number of tunables grows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    """os.getenv, but an empty value counts as unset.

    ``os.getenv`` returns "" for a variable that's present but blank, so a
    commented-out-by-emptying line in .env (``SSH_KNOWN_HOSTS=``) would
    override the default with an empty string rather than leave it alone -
    which for a path means Path(""), i.e. the current directory. Blank
    almost always means "I didn't set this".
    """
    value = os.getenv(name)
    return value if value else default


@dataclass(frozen=True)
class Settings:
    # Where the four config_*.json files (see services/app_config.py) live.
    # Relative to CWD by default, same fragile-by-default convention as
    # every path below - mcp_server is always run from its own directory
    # (run_mcp_server.bat cd's there first), so "configs" resolves.
    configs_dir: Path = Path(_env("MCP_CONFIGS_DIR", "configs"))
    # Loopback by default, deliberately. This server has no authentication
    # of its own: anything that can reach the port can call every
    # registered tool with arbitrary arguments, and the Flask app is not
    # in that path, so no amount of auth over there protects this. Binding
    # to 0.0.0.0 exposes that to the whole network, which should be a
    # decision someone makes on purpose rather than a default they
    # inherit. Override MCP_HOST only once something in front of it
    # (reverse proxy, VPN, firewall) is doing the authenticating.
    host: str = _env("MCP_HOST", "127.0.0.1")
    port: int = int(_env("MCP_PORT", "8010"))
    # known_hosts file used to verify SSH host keys. Defaults to the same
    # one the ssh command-line client uses, so hosts you've already
    # connected to from this machine are trusted without extra setup.
    ssh_known_hosts: Path = Path(
        _env("SSH_KNOWN_HOSTS", str(Path.home() / ".ssh" / "known_hosts"))
    )
    # "reject" (default) or "auto". Rejecting an unknown host key is the
    # point of having known_hosts at all: it's what makes a
    # machine-in-the-middle visible, and - more importantly in practice -
    # what makes a host key that *changed* an error instead of a silent
    # accept. "auto" trusts whatever key answers first and records it,
    # which is fine for a throwaway lab and wrong everywhere else.
    ssh_host_key_policy: str = _env("SSH_HOST_KEY_POLICY", "reject")
    # Where logging_setup.configure_logging() writes server.log and
    # errors.report() writes per-reference error files. Relative to CWD by
    # default, same convention as the paths above.
    log_dir: Path = Path(_env("MCP_LOG_DIR", ".logs"))
    # Shared secret, same value both directions. Most chat_app -> mcp_server
    # calls (fetch_capabilities, ...)
    # carry no credential of their own because they're all read/administrative
    # actions a trusting deployment accepts from its own chat_app. One call
    # needs real auth, though: this server's own POST /upload (see upload_routes.py) checks the
    # same token on the way IN, since chat_app's Chat/api/upload proxies a
    # user's dropped file here and the receiving end shouldn't accept that
    # from anything else reachable on the network. Blank by default (from
    # .env, unset until someone configures it) so it
    # fails loudly rather than silently accepting an unauthenticated request.
    internal_api_token: str = _env("INTERNAL_API_TOKEN", "")
    # Where POST /upload (upload_routes.py) writes files a chat_app user
    # dropped into a command-form modal, before a tool param
    # that expects a real server-side path gets one.
    # Relative to CWD by default, same convention as every path above.
    uploads_dir: Path = Path(_env("MCP_UPLOADS_DIR", ".data/uploads"))
    pdf_merger_store_dir: Path = Path(_env("MCP_PDF_MERGER_STORE_DIR", "specifics/pdf_merger/.data/store"))
    pdf_merger_config_path: Path = Path(_env("MCP_PDF_MERGER_CONFIG_PATH", "specifics/pdf_merger/configs/config_pdf_merger.json"))
    pdf_merger_public_base_url: str = _env("MCP_PDF_MERGER_PUBLIC_BASE_URL", "")
    pdf_merger_signing_key: str = _env("PDF_MERGER_SIGNING_KEY", "")
    # Where capability-owned job watchers keep their state
    # records. Relative to CWD, like uploads_dir.
    watchers_dir: Path = Path(_env("MCP_WATCHERS_DIR", ".data/watchers"))
    email_audit_path: Path = Path(_env("MCP_EMAIL_AUDIT_PATH", "specifics/email/.data/audit.db"))
    # Per-user memory notes (capabilities/memory). Runtime state: gitignored.
    memory_db_path: Path = Path(_env("MCP_MEMORY_DB_PATH", "specifics/memory/.data/memory.db"))
    # Support tickets (services/tickets.py): SQLite file, and the optional Laya
    # agent's MCP address (http://host:9111/mcp) used to group and tag tickets.
    # Blank LAYA_URL skips Laya; tickets still work.
    tickets_db_path: Path = Path(_env("MCP_TICKETS_DB_PATH", "specifics/tickets/.data/tickets.db"))
    laya_url: str = _env("LAYA_URL", "")
    # db_gateway, where ember_api keeps per-account notes; the notes capability reads the ones an
    # account shared with agents. The instance must list the connection (db_gateway's
    # configs/config_connections.json). The request carries INTERNAL_API_TOKEN.
    db_gateway_url: str = _env("DB_GATEWAY_URL", "http://127.0.0.1:8071")
    db_gateway_instance: str = _env("DB_GATEWAY_INSTANCE", "mcp_server")
    db_gateway_connection: str = _env("DB_GATEWAY_CONNECTION", "data")
    # Obsidian Local REST API. Never include the address or credential in settings repr.
    obsidian_base_url: str = field(default=_env("OBSIDIAN_BASE_URL", "https://127.0.0.1:27124"), repr=False)
    obsidian_api_key: str = field(default=_env("OBSIDIAN_API_KEY", ""), repr=False)
    obsidian_timeout: float = float(_env("OBSIDIAN_TIMEOUT", "5"))
    obsidian_verify_tls: bool = _env("OBSIDIAN_VERIFY_TLS", "true").lower() != "false"
    obsidian_allow_write: bool = _env("OBSIDIAN_ALLOW_WRITE", "false").lower() == "true"
    obsidian_vault_path: str = _env("OBSIDIAN_VAULT_PATH", "")
    obsidian_index_path: Path = Path(_env("OBSIDIAN_INDEX_PATH", "specifics/obsidian/.data/index.db"))
    obsidian_ollama_url: str = _env("OBSIDIAN_OLLAMA_URL", "http://127.0.0.1:11434")
    obsidian_embed_model: str = _env("OBSIDIAN_EMBED_MODEL", "nomic-embed-text")
    obsidian_refresh_seconds: float = float(_env("OBSIDIAN_REFRESH_SECONDS", "60"))
    ember_api_url: str = _env("EMBER_API_URL", "http://127.0.0.1:8030")
    # Tavily API key for the web_research capability. Blank until set in .env;
    # the tools then fail with a message naming the variable.
    tavily_api_key: str = _env("TAVILY_API_KEY", "")
    # Firecrawl key and optional self-hosted address for the firecrawl capability.
    # Blank key: the tools fail naming the variable (a self-hosted URL may run keyless).
    firecrawl_api_key: str = _env("FIRECRAWL_API_KEY", "")
    firecrawl_api_url: str = _env("FIRECRAWL_API_URL", "")

    # Video downloads stay on armory's listener; only the public origin is configurable.
    media_store_dir: Path = Path(_env("MCP_MEDIA_STORE_DIR", "specifics/media_downloader/.data/store"))
    media_log_dir: Path = Path(_env("MCP_MEDIA_LOG_DIR", "specifics/media_downloader/.logs"))
    media_config_path: Path = Path(_env("MCP_MEDIA_CONFIG_PATH", "specifics/media_downloader/configs/config_media_downloader.json"))
    media_public_base_url: str = _env("MCP_MEDIA_PUBLIC_BASE_URL", "")
    media_signing_key: str = _env("MCP_MEDIA_SIGNING_KEY", "")

    # Folders the read-only capabilities look at, relative to apps/armory/.
    # usage_report: ai_agent's usage log. vault: the Obsidian vault.
    # repo_reader: the folder that holds the project repos.
    usage_dir: Path = Path(_env("MCP_USAGE_DIR", "../garrison/.data/usage"))
    vault_dir: Path = Path(_env("MCP_VAULT_DIR", "../../../../Brain"))
    workspace_dir: Path = Path(_env("MCP_WORKSPACE_DIR", "../../../.."))

    @property
    def email_config_path(self) -> Path:
        return self.configs_dir / "config_email.json"

    @property
    def tickets_config_path(self) -> Path:
        return self.configs_dir / "config_tickets.json"

    @property
    def extensions_config_path(self) -> Path:
        return self.configs_dir / "config_extensions.json"

    @property
    def capabilities_config_path(self) -> Path:
        return self.configs_dir / "config_capabilities.json"


settings = Settings()
