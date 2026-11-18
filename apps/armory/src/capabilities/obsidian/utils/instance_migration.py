"""Import the saved Stronghold instance record and acknowledge durable receipt."""

import asyncio
import logging
import sqlite3

import httpx
from cryptography.fernet import InvalidToken

from src.capabilities.obsidian.utils.gateway import ObsidianGatewayError
from src.citadel_auth import AuthError, service_client
from src.citadel_auth.brain_migration import acknowledgement, challenge, unseal

_LOG = logging.getLogger(__name__)
_PATH = "/brains/instance-migration"


async def migrate(store, keyring, catalog):
    async with service_client(keyring, "stronghold", timeout=5, trust_env=False) as client:
        while True:
            try:
                imported, pending = await asyncio.to_thread(store.migration)
                if not imported:
                    private, proof = challenge(keyring)
                    response = await client.post(catalog.url("stronghold") + _PATH, json={"proof": proof})
                    response.raise_for_status()
                    snapshot = await unseal(keyring, private, proof, response.json())
                    await asyncio.to_thread(store.import_once, snapshot)
                    _, pending = await asyncio.to_thread(store.migration)
                if pending:
                    proof = acknowledgement(keyring, *pending)
                    response = await client.post(catalog.url("stronghold") + _PATH + "/ack", json={"proof": proof})
                    response.raise_for_status()
                    await asyncio.to_thread(store.migrated)
                return
            except (AuthError, InvalidToken, httpx.HTTPError, OSError, ValueError, KeyError, TypeError,
                    AttributeError, ObsidianGatewayError, sqlite3.Error):
                _LOG.warning("Instance Brain migration will retry")
                catalog.refresh_soon()
                await asyncio.sleep(15)
