"""Vault: search and read the Obsidian vault, read-only."""

from src.services.capability_base import Capability


class Vault(Capability):
    id = "vault"
    label = "Vault"


CAPABILITY = Vault()
