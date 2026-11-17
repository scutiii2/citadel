"""Stronghold's process identity and signed outbound HTTP configuration."""

from src.citadel_auth import ServiceAuth, from_env

keyring = from_env("stronghold")


def authenticate(client, audience: str, identity=None):
    client.auth = ServiceAuth(identity or keyring, audience)
    return client
