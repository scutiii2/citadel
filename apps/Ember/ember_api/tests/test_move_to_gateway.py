"""scripts/move_to_gateway: copies legacy per-account rows into db_gateway, once."""

from __future__ import annotations

import asyncio
from pathlib import Path

from scripts.move_to_gateway import move
from src.db import Database
from src.models import Account, AccountCapability, NavPreference, PromptTemplate, UserExtension
from src.db import utcnow
from tests.conftest import FakeDbGateway


ALL_ONE = {"nav_preferences": 1, "account_capabilities": 1, "prompt_templates": 1, "user_extensions": 1}
ALL_ZERO = {name: 0 for name in ALL_ONE}


async def seeded(tmp_path: Path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}")
    await database.create_tables()
    async with database.sessions() as session:
        session.add(Account(id=1, uid="u1", username="a", email="a@example.test", password_hash="x"))
        session.add(NavPreference(account_id=1, page_order=["/", "/a"], pinned=["/a"], hidden=[]))
        session.add_all([
            AccountCapability(account_id=1, kind="capability", item_id="pdf"),
            AccountCapability(account_id=1, kind="extension", item_id="notes"),
        ])
        now = utcnow()
        session.add(PromptTemplate(account_id=1, name="Review", name_key="review", body="b", created_at=now, updated_at=now))
        session.add(UserExtension(
            account_id=1, slug="notes", label="Notes", url="https://n.example.test/mcp", headers_encrypted="tok",
            enabled=True, created_at=now, updated_at=now,
        ))
        await session.commit()
    return database


def test_copies_rows_and_leaves_existing_documents_alone(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, store = await seeded(tmp_path), FakeDbGateway()
        try:
            assert await move(database, store, dry_run=False) == ALL_ONE
            nav = await store.get("nav_preferences", "u1")
            assert (nav["order"], nav["pinned"], nav["owner"]) == (["/", "/a"], ["/a"], "u1")
            caps = await store.get("account_capabilities", "u1")
            assert (caps["capabilities"], caps["extensions"]) == (["pdf"], ["notes"])
            (template,) = [d for (c, _), d in store.records.items() if c == "prompt_templates"]
            assert (template["name"], template["owner"], len(template["id"])) == ("Review", "u1", 32)
            extension = await store.get("user_extensions", "u1:notes")
            assert (extension["headers_encrypted"], extension["enabled"]) == ("tok", True)

            await store.put("nav_preferences", "u1", {**nav, "order": ["/changed"]})  # changed after the move
            assert await move(database, store, dry_run=False) == ALL_ZERO
            assert (await store.get("nav_preferences", "u1"))["order"] == ["/changed"]
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    async def scenario() -> None:
        database, store = await seeded(tmp_path), FakeDbGateway()
        try:
            assert await move(database, store, dry_run=True) == ALL_ONE
            assert store.records == {}
        finally:
            await database.dispose()

    asyncio.run(scenario())
