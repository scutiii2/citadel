"""Real signed credentials for Stronghold boundary tests."""
import asyncio
import jwt
from collections.abc import Mapping

from src.citadel_auth import ServiceAuth, verify_assertion
from src.citadel_auth.testing import requester_headers

stack = None


class IdentityHeaders(Mapping):
    """Lazy requester fixture; identities are generated after session keys exist."""
    def __init__(self, **claims):
        self.claims = claims

    def __getitem__(self, key):
        return identity(**self.claims)[key]

    def __iter__(self):
        return iter(identity(**self.claims))

    def __len__(self):
        return len(identity(**self.claims))

    def items(self):
        return identity(**self.claims).items()


def identity(uid="u-1", username="ana", email="ana@example.com"):
    return requester_headers(stack["portcullis"], uid, username, email) if uid else {"X-Citadel-Requester": ""}


def service_auth():
    return ServiceAuth(stack["portcullis"], "stronghold")


def caller(request, audience):
    return jwt.decode(request.headers["Authorization"][7:], stack["stronghold"].private_key.public_key(),
                      algorithms=["EdDSA"], audience=audience)["iss"]


def requester(request, audience="armory"):
    # Real signature validation; fixtures contain no private credentials from the deployment.
    return jwt.decode(request.headers["X-Citadel-Requester"], stack["portcullis"].private_key.public_key(),
                      algorithms=["EdDSA"], audience=audience)
