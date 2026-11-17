"""Citadel service identity, requester identity, and HTTP authentication."""

from .asgi import ServiceAuthMiddleware, current_caller
from .client import ServiceAuth, requester_header, requester_meta, service_client
from .errors import AuthError, Forbidden
from .keyring import Keyring
from .requester import Requester, current_requester, current_requester_token, mint_requester, verify_requester, requester_context
from .settings import from_env
from .tokens import Caller, sign_assertion, verify_assertion

__all__ = ["AuthError", "Forbidden", "Keyring", "Caller", "Requester", "ServiceAuth",
    "ServiceAuthMiddleware", "current_caller", "current_requester", "current_requester_token",
    "from_env", "mint_requester", "requester_header", "requester_meta", "requester_context", "service_client",
    "sign_assertion", "verify_assertion", "verify_requester"]
