"""Every permission ember_api knows about. The Administrator role always
holds all of them (see AuthService.ensure_bootstrap_admin)."""

from types import MappingProxyType

CHAT_USE = "chat.use"
TOOLS_VIEW = "tools.view"
TOOLS_EXECUTE = "tools.execute"
CHAT_SHARE = "chat.share"
EXTENSIONS_PERSONAL_MANAGE = "extensions.personal.manage"
FILES_UPLOAD = "files.upload"
FILES_DOWNLOAD = "files.download"
ACCOUNTS_VIEW = "accounts.view"
ACCOUNTS_MANAGE = "accounts.manage"
ACCOUNTS_DELETE = "accounts.delete"
ROLES_VIEW = "roles.view"
ROLES_MANAGE = "roles.manage"
ROLES_ASSIGN = "roles.assign"
INVITES_MANAGE = "invites.manage"
SETTINGS_MANAGE = "settings.manage"
CAPABILITIES_MANAGE = "capabilities.manage"
USAGE_ALL_VIEW = "usage.all.view"
EXTENSIONS_MANAGE = "extensions.manage"
LOGS_VIEW = "logs.view"
LOGS_ERRORS_VIEW = "logs.errors.view"
LOGS_CHAT_VIEW = "logs.chat.view"
LOGS_CHAT_PROMPTS_VIEW = "logs.chat.prompts.view"
CONFIG_ISSUES_VIEW = "config.issues.view"
TRAFFIC_VIEW = "traffic.view"
AGENTS_MANAGE = "agents.manage"
TICKETS_CREATE = "tickets.create"
TICKETS_MANAGE = "tickets.manage"
BRAIN_INSTANCE_PUBLISH = "brain.instance.publish"

ALL_PERMISSIONS = MappingProxyType({
    BRAIN_INSTANCE_PUBLISH: "Publish durable knowledge to the shared Instance Brain",
    CHAT_USE: "Chat with ai_agent instances",
    TOOLS_VIEW: "Browse tools, capabilities, help and resources",
    TOOLS_EXECUTE: "Run tools directly and through chat agents",
    CHAT_SHARE: "Create public read-only links to your chats",
    EXTENSIONS_PERSONAL_MANAGE: "Add, edit and remove your own MCP extensions",
    FILES_UPLOAD: "Upload files to tools and attach files to chat",
    FILES_DOWNLOAD: "Download files from mcp_server",
    ACCOUNTS_VIEW: "View accounts and their status",
    ACCOUNTS_MANAGE: "Edit accounts, enable or disable them and resend verification",
    ACCOUNTS_DELETE: "Delete accounts",
    ROLES_VIEW: "View roles and permissions",
    ROLES_MANAGE: "Create, edit and delete roles and change their permissions",
    ROLES_ASSIGN: "Assign and remove account roles within your own permissions",
    INVITES_MANAGE: "Create, list and revoke invitations",
    SETTINGS_MANAGE: "Change workspace settings",
    CAPABILITIES_MANAGE: "Enable, disable and discover shared capabilities",
    USAGE_ALL_VIEW: "View usage across all accounts",
    EXTENSIONS_MANAGE: "Add and remove mcp_server extensions (other MCP servers offered to every client)",
    LOGS_VIEW: "Read the activity log (logins, account and admin changes)",
    LOGS_ERRORS_VIEW: "Read the error log",
    LOGS_CHAT_VIEW: "Read the chat-turn log (every account's questions and answers)",
    LOGS_CHAT_PROMPTS_VIEW: "Read the prompts each agent received in the chat-turn log (needs logs.chat.view)",
    CONFIG_ISSUES_VIEW: "See problems in ember_api's config and secret files",
    TRAFFIC_VIEW: "See network traffic charts (requests, latency, upstream calls)",
    AGENTS_MANAGE: "Create, edit and remove ai_agent agents (provider, gateway, persona, tools)",
    TICKETS_CREATE: "Report bugs, suggest features and follow your own tickets",
    TICKETS_MANAGE: "See every ticket, triage them and set status, priority and assignee",
})

# Staff permissions: an account whose email is not verified does not hold them, even when
# config_app.json sets require_email_verification to false (see Account.permission_names).
STAFF_PERMISSIONS = frozenset({
    ACCOUNTS_VIEW, ACCOUNTS_MANAGE, ACCOUNTS_DELETE, ROLES_VIEW, ROLES_MANAGE, ROLES_ASSIGN,
    INVITES_MANAGE, SETTINGS_MANAGE, CAPABILITIES_MANAGE, EXTENSIONS_MANAGE, AGENTS_MANAGE,
    LOGS_VIEW, LOGS_ERRORS_VIEW, LOGS_CHAT_VIEW, LOGS_CHAT_PROMPTS_VIEW, CONFIG_ISSUES_VIEW,
    TRAFFIC_VIEW, USAGE_ALL_VIEW, TICKETS_MANAGE,
})

ADMIN_ROLE = "Administrator"

# What the default role (config_app.json's default_role) starts with when it
# has to be created. Only applied on creation: later edits by an admin stick.
DEFAULT_ROLE_PERMISSIONS = (
    CHAT_USE, TOOLS_VIEW, TOOLS_EXECUTE, CHAT_SHARE,
    EXTENSIONS_PERSONAL_MANAGE, FILES_UPLOAD, FILES_DOWNLOAD, TICKETS_CREATE,
)

ADMIN_PERMISSIONS = (
    ACCOUNTS_VIEW, ACCOUNTS_MANAGE, ACCOUNTS_DELETE, ROLES_VIEW,
    ROLES_MANAGE, ROLES_ASSIGN, INVITES_MANAGE, SETTINGS_MANAGE,
)

def is_known_permission(name: str) -> bool:
    return name in ALL_PERMISSIONS


def permission_description(name: str) -> str | None:
    return ALL_PERMISSIONS.get(name)
