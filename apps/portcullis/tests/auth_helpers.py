"""Verify real outgoing signatures in mocks without filesystem I/O."""
import jwt
from src.services import service_auth


def requester(request):
    raw = request.headers.get("X-Citadel-Requester")
    if not raw:
        return {"sub": "", "username": "", "email": ""}
    return jwt.decode(raw, service_auth.keyring.private_key.public_key(), algorithms=["EdDSA"],
                      issuer="portcullis", options={"verify_aud": False})


def assertion(request, audience=None):
    claims = jwt.decode(request.headers["Authorization"].removeprefix("Bearer "),
                        service_auth.keyring.private_key.public_key(), algorithms=["EdDSA"],
                        issuer="portcullis", audience=audience, options={"verify_aud": audience is not None})
    assert claims["exp"] - claims["iat"] == 60
    return claims
