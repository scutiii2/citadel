"""Citadel service identity, requester identity, and HTTP authentication."""

from .catalog import (
    CatalogTransport, DEFAULTS as SERVICE_DEFAULTS, ServiceCatalog, UnknownService, advertised_url,
    checked_address, logical_url, resolved,
)

from .asgi import ServiceAuthMiddleware, current_caller
from .client import ServiceAuth, requester_header, requester_meta, service_client
from .errors import AuthError, Forbidden
from .keyring import Keyring
from .paths import cache_dir, data_dir
from .rootenv import apply_root_env, root_overrides
from .requester import Requester, current_requester, current_requester_token, mint_requester, verify_requester, requester_context, requester_token_provider
from .settings import from_env
from .tokens import Caller, sign_assertion, verify_assertion

__all__ = ["CatalogTransport", "SERVICE_DEFAULTS", "ServiceCatalog", "UnknownService",
    "advertised_url", "checked_address", "logical_url", "resolved", "AuthError", "Forbidden", "Keyring", "Caller", "Requester", "ServiceAuth",
    "ServiceAuthMiddleware", "current_caller", "current_requester", "current_requester_token",
    "apply_root_env", "cache_dir", "root_overrides", "data_dir", "from_env", "mint_requester", "requester_header", "requester_meta", "requester_context", "requester_token_provider", "service_client",
    "sign_assertion", "verify_assertion", "verify_requester"]
