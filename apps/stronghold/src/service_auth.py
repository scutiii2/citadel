"""Stronghold's process identity and signed outbound HTTP configuration."""

from pathlib import Path

from src.citadel_auth import data_dir
from src.citadel_auth import ServiceAuth, from_env

keyring = from_env("stronghold", data_dir=data_dir(Path(__file__).resolve().parents[1]))


def authenticate(client, audience: str, identity=None):
    client.auth = ServiceAuth(identity or keyring, audience)
    return client
