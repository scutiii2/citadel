"""Copies per-account rows that now live in db_gateway out of ember_api's database.

    python -m scripts.move_to_gateway            (copy, then print what was copied)
    python -m scripts.move_to_gateway --dry-run  (print the counts only)

Covers nav preferences, account capabilities, prompt templates and private extensions.
Migrated templates get new string ids. Safe to run again: a document already in the
gateway is left alone, so changes made since the move are never overwritten. The old tables are
not touched; drop them in a later migration once you have checked the data. Needs db_gateway
running and the same config_app.json and .env that ember_api uses.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from sqlalchemy import select

from src.config import load_settings
from src.db import Database, utcnow
import uuid

from src.models import Account, AccountCapability, NavPreference, PromptTemplate, UserExtension
from src.services.account_capability_service import COLLECTION as CAPABILITIES
from src.services.db_gateway import DbGatewayClient, DbGatewayError, DocumentStore
from src.services.nav_preference_service import COLLECTION as NAV
from src.services.template_service import COLLECTION as TEMPLATES, _key as template_key
from src.services.user_extension_service import COLLECTION as EXTENSIONS
from src.utils.config_loader import load_env_secrets


async def move(database: Database, store: DocumentStore, dry_run: bool) -> dict[str, int]:
    """Returns how many documents were (or, for a dry run, would be) created per collection."""
    created = {NAV: 0, CAPABILITIES: 0, TEMPLATES: 0, EXTENSIONS: 0}
    async with database.sessions() as session:
        uids = dict((await session.execute(select(Account.id, Account.uid))).all())
        nav_rows = (await session.scalars(select(NavPreference))).all()
        capability_rows = (await session.scalars(select(AccountCapability))).all()
        template_rows = (await session.scalars(select(PromptTemplate))).all()
        extension_rows = (await session.scalars(select(UserExtension))).all()

    for row in nav_rows:
        uid = uids.get(row.account_id)
        doc = {
            "owner": uid, "order": list(row.page_order), "pinned": list(row.pinned), "hidden": list(row.hidden),
            "updated_at": row.updated_at.isoformat(timespec="seconds"),
        }
        created[NAV] += await _create(store, NAV, uid, doc, dry_run)

    grouped: dict[str, dict[str, list[str]]] = {}
    for row in capability_rows:
        uid = uids.get(row.account_id)
        if uid is not None:
            grouped.setdefault(uid, {"capability": [], "extension": []})[row.kind].append(row.item_id)
    for uid, kinds in grouped.items():
        doc = {
            "owner": uid, "capabilities": sorted(kinds["capability"]), "extensions": sorted(kinds["extension"]),
            "updated_at": utcnow().isoformat(timespec="seconds"),
        }
        created[CAPABILITIES] += await _create(store, CAPABILITIES, uid, doc, dry_run)

    for row in template_rows:
        uid = uids.get(row.account_id)
        if uid is None:
            continue
        doc = {
            "id": uuid.uuid4().hex, "owner": uid, "name": row.name, "name_key": row.name_key, "body": row.body,
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        }
        created[TEMPLATES] += await _create(store, TEMPLATES, template_key(uid, row.name), doc, dry_run)

    for row in extension_rows:
        uid = uids.get(row.account_id)
        if uid is None:
            continue
        doc = {
            "owner": uid, "slug": row.slug, "label": row.label, "description": row.description, "url": row.url,
            "headers_encrypted": row.headers_encrypted, "enabled": row.enabled,
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
        }
        created[EXTENSIONS] += await _create(store, EXTENSIONS, f"{uid}:{row.slug}", doc, dry_run)
    return created


async def _create(store: DocumentStore, collection: str, key: str | None, doc: dict, dry_run: bool) -> int:
    """`key` is the document key; for the per-account collections that is the account uid."""
    if key is None:
        return 0
    if dry_run:
        return 1 if await store.get(collection, key) is None else 0
    return 1 if await store.create(collection, key, doc) else 0


async def run(dry_run: bool) -> str:
    settings = load_settings()
    database = Database(settings.database_url)
    gateway = settings.db_gateway
    internal_token = load_env_secrets(settings.env_path).get("INTERNAL_API_TOKEN")
    async with httpx.AsyncClient(base_url=gateway.url, timeout=httpx.Timeout(5.0)) as http:
        store = DbGatewayClient(http, gateway.instance, gateway.connection, internal_token or None)
        try:
            counts = await move(database, store, dry_run)
        finally:
            await database.dispose()
    verb = "would copy" if dry_run else "copied"
    return "\n".join(f"{verb} {n} document(s) into {name}" for name, n in counts.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(asyncio.run(run(args.dry_run)))
    except DbGatewayError as error:
        print(f"Nothing more was copied: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
