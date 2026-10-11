# Rotating Shop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Ascension shop offers each account 5 limited-stock copy packages that rotate every 6 hours, shown as cards, and the collection cards get a subtle hover lift.

**Architecture:** Offers are derived from `(owner, rotation)` by a seeded pick (`ShopOffers`, pure). Only purchase counts are stored (`shop_purchases`, schema version 3 with an upgrade step). `ShopService` lists the window and buys by `(rotation, slot)` inside the existing idempotent transaction. The web shop reads `GET /ascension/shop` and counts down on the device clock.

**Tech Stack:** Python 3.11 + FastAPI + sqlite3 + pytest (`apps/ascension`, venv `.venv_ascension`); Vue 3 + TypeScript + Pinia + Vitest (`apps/ascension/web`).

**Spec:** `docs/superpowers/specs/2026-10-12-rotating-shop-design.md`

## Global Constraints

- Rotation is `floor(now / shop_rotation_seconds)`; default `shop_rotation_seconds` 21600; default `shop_offers` 5, allowed 1 to 12.
- Stock by tier (catalog data): common 3, rare 3, unique 2, royal 1, legendary 1. Tier weights: common 40, rare 30, unique 18, royal 8, legendary 4.
- Forbidden Ascended and the forbidden tier are never offered. Offers in one window are for distinct Ascended.
- EMBLEM purchases and selling copies are unchanged.
- Errors: stale rotation = 409 "the shop has refreshed; look at the new offers"; sold out = 409 `SoldOut`; unknown slot = 400; insufficient Insignia and "fighting" refusals keep their current 409s.
- Database version 2 upgrades to 3 by adding `shop_purchases`; any other version still raises `RuntimeError("database schema version N is not supported ...")`.
- Python: run tests with `.venv_ascension\Scripts\python -m pytest` from `apps/ascension`. Web: `npx vitest run` and `npx vue-tsc --noEmit` from `apps/ascension/web`.
- Hover lift is off under `prefers-reduced-motion`. Border radius must use tokens (`radiusScale.test.ts` enforces it).
- Commit only when the user says "commit"; the steps below name the commit boundaries, run them only on that word.

---

## Phase A: Backend (commit 1)

### Task 1: Catalog shop data and `ShopOffers`

**Files:**
- Modify: `apps/ascension/configs/ascension_catalog.json` (add a top-level `"shop"` key)
- Modify: `apps/ascension/src/ascension/catalog.py` (class `ShopSpec`, `Catalog.shop`, validation)
- Create: `apps/ascension/src/ascension/shop_offers.py`
- Modify: `apps/ascension/tests/ascension/helpers.py` (add `FixedOffers`)
- Test: `apps/ascension/tests/ascension/test_shop_offers.py`, `apps/ascension/tests/ascension/test_catalog.py`

**Interfaces:**
- Produces: `Catalog.shop: ShopSpec` with `stock: Mapping[str, int]` and `tier_weights: Mapping[str, float]` (keys are the five regular tier ids).
- Produces: `Offer(slot: int, ascended_id: str, tier_id: str, stock: int)`, `ShopWindow(rotation: int, refreshes_at: float, offers: tuple[Offer, ...])`, `ShopOffers(catalog, rotation_seconds: float, offer_count: int)` with `rotation_at(now: float) -> int` and `window(owner: str, now: float) -> ShopWindow`.
- Produces (tests): `FixedOffers(*offers, seconds=21600.0)` with the same two methods.

- [ ] **Step 1: Add the shop data to the catalog JSON**

Add this key next to `"economy"` in `configs/ascension_catalog.json`:

```json
  "shop": {
    "stock": { "common": 3, "rare": 3, "unique": 2, "royal": 1, "legendary": 1 },
    "tier_weights": { "common": 40, "rare": 30, "unique": 18, "royal": 8, "legendary": 4 }
  },
```

- [ ] **Step 2: Write the failing catalog test**

Append to `tests/ascension/test_catalog.py` (it already imports `Catalog`, `CatalogError`, `load_raw`; if `load_raw` is not imported there, import it from `tests.ascension.env`):

```python
def test_the_shop_section_covers_the_regular_tiers():
    from tests.ascension.env import CATALOG

    assert set(CATALOG.shop.stock) == {t.id for t in CATALOG.regular_tiers}
    assert set(CATALOG.shop.tier_weights) == set(CATALOG.shop.stock)
    assert CATALOG.shop.stock["common"] == 3 and CATALOG.shop.stock["legendary"] == 1


@pytest.mark.parametrize("mutate", [
    lambda raw: raw.pop("shop"),
    lambda raw: raw["shop"]["stock"].pop("rare"),
    lambda raw: raw["shop"]["stock"].update(common=0),
    lambda raw: raw["shop"]["tier_weights"].update(common=0),
    lambda raw: raw["shop"]["stock"].update(forbidden=1),
])
def test_a_bad_shop_section_is_refused(mutate):
    from tests.ascension.env import load_raw

    raw = load_raw()
    mutate(raw)
    with pytest.raises(CatalogError):
        Catalog(raw)
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_catalog.py -q`
Expected: FAIL (`Catalog` has no attribute `shop`).

- [ ] **Step 3: Implement `ShopSpec` in `catalog.py`**

Add near `Levels`:

```python
@dataclass(frozen=True)
class ShopSpec:
    """Per regular tier: how many times one offer can be bought, and how likely the tier is to be offered."""

    stock: Mapping[str, int]
    tier_weights: Mapping[str, float]
```

In `_build`, after `self.levels = ...`:

```python
        shop = _require(raw, "shop", "catalog")
        self.shop = ShopSpec(dict(_require(shop, "stock", "shop")), dict(_require(shop, "tier_weights", "shop")))
```

At the end of `_validate`:

```python
        regular_ids = {t.id for t in self.regular_tiers}
        if set(self.shop.stock) != regular_ids or set(self.shop.tier_weights) != regular_ids:
            raise CatalogError("shop stock and tier_weights must list exactly the regular tiers")
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in self.shop.stock.values()):
            raise CatalogError("shop stock must be a whole number of at least 1 per tier")
        if any(isinstance(w, bool) or not isinstance(w, (int, float)) or w <= 0 for w in self.shop.tier_weights.values()):
            raise CatalogError("shop tier_weights must be positive numbers")
```

Run the catalog tests again. Expected: PASS. Also run `.venv_ascension\Scripts\python -m pytest tests/ascension -q -x` and fix any catalog test that builds a raw catalog by hand without `shop` (add `"shop"` from `load_raw()`).

- [ ] **Step 4: Write the failing offers tests**

Create `tests/ascension/test_shop_offers.py`:

```python
from src.ascension.shop_offers import ShopOffers
from tests.ascension.env import CATALOG

ROTATION = 21600.0
NOW = 1_000_000.0


def offers(count=5):
    return ShopOffers(CATALOG, ROTATION, count)


def test_the_same_account_sees_the_same_window_within_a_rotation():
    first = offers().window("ann", NOW)
    again = offers().window("ann", NOW + 60)
    assert first == again
    assert first.rotation == int(NOW // ROTATION)
    assert first.refreshes_at == (first.rotation + 1) * ROTATION


def test_the_window_changes_with_the_rotation_and_the_account():
    base = offers().window("ann", NOW)
    later = offers().window("ann", NOW + ROTATION)
    other = offers().window("bob", NOW)
    assert later.rotation == base.rotation + 1 and later.offers != base.offers
    assert other.offers != base.offers


def test_offers_are_distinct_regular_ascended_with_stock_by_tier():
    window = offers().window("ann", NOW)
    ids = [o.ascended_id for o in window.offers]
    assert len(window.offers) == 5 and len(set(ids)) == 5
    assert [o.slot for o in window.offers] == [0, 1, 2, 3, 4]
    for offer in window.offers:
        assert not CATALOG.ascended(offer.ascended_id).forbidden
        assert offer.tier_id in CATALOG.shop.stock
        assert offer.stock == CATALOG.shop.stock[offer.tier_id]


def test_the_count_is_limited_by_the_number_of_regular_ascended():
    regular = [s for s in CATALOG.all_ascendeds() if not s.forbidden]
    assert len(offers(12).window("ann", NOW).offers) == min(12, len(regular))


def test_lower_tiers_are_offered_more_often():
    from collections import Counter

    seen = Counter()
    for n in range(300):
        for offer in offers().window(f"player{n}", NOW).offers:
            seen[offer.tier_id] += 1
    assert seen["common"] > seen["rare"] > seen["unique"] > seen["legendary"]
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_shop_offers.py -q`
Expected: FAIL (module missing).

- [ ] **Step 5: Implement `shop_offers.py`**

```python
"""The rotating shop window: which copy packages an account may buy now.

Offers are not stored. They are derived from (owner, rotation), so the same account sees the
same offers until the rotation changes, and no job has to run at the turn of a rotation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.ascension.catalog import Catalog
from src.ascension.runtime import SeededRandom


@dataclass(frozen=True)
class Offer:
    slot: int
    ascended_id: str
    tier_id: str
    stock: int


@dataclass(frozen=True)
class ShopWindow:
    rotation: int
    refreshes_at: float
    offers: tuple[Offer, ...]


class ShopOffers:
    def __init__(self, catalog: Catalog, rotation_seconds: float, offer_count: int) -> None:
        self._catalog = catalog
        self._seconds = rotation_seconds
        self._count = offer_count

    def rotation_at(self, now: float) -> int:
        return int(now // self._seconds)

    def window(self, owner: str, now: float) -> ShopWindow:
        rotation = self.rotation_at(now)
        digest = hashlib.sha256(f"{owner}:{rotation}".encode()).digest()
        rng = SeededRandom(int.from_bytes(digest[:8], "big"))
        pool = sorted(s.id for s in self._catalog.all_ascendeds() if not s.forbidden)
        offers: list[Offer] = []
        for slot in range(min(self._count, len(pool))):
            ascended_id = pool.pop(int(rng.next() * len(pool)))
            tier_id = self._pick_tier(rng.next())
            offers.append(Offer(slot, ascended_id, tier_id, self._catalog.shop.stock[tier_id]))
        return ShopWindow(rotation, (rotation + 1) * self._seconds, tuple(offers))

    def _pick_tier(self, draw: float) -> str:
        weights = self._catalog.shop.tier_weights
        tiers = [t.id for t in self._catalog.regular_tiers]
        target = draw * sum(weights[t] for t in tiers)
        for tier_id in tiers:
            target -= weights[tier_id]
            if target < 0:
                return tier_id
        return tiers[-1]
```

- [ ] **Step 6: Add `FixedOffers` to `tests/ascension/helpers.py`**

```python
class FixedOffers:
    """A shop window with the given offers, for tests that need a known Ascended or stock."""

    def __init__(self, *offers, seconds: float = 21600.0) -> None:
        self.offers = tuple(offers)
        self.seconds = seconds

    def rotation_at(self, now: float) -> int:
        return int(now // self.seconds)

    def window(self, owner: str, now: float):
        from src.ascension.shop_offers import ShopWindow

        rotation = self.rotation_at(now)
        return ShopWindow(rotation, (rotation + 1) * self.seconds, self.offers)
```

- [ ] **Step 7: Run and verify**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_shop_offers.py tests/ascension/test_catalog.py -q`
Expected: PASS.

### Task 2: Repository table, upgrade and counters

**Files:**
- Modify: `apps/ascension/src/ascension/repository.py`
- Test: `apps/ascension/tests/ascension/test_repository.py`

**Interfaces:**
- Produces on `AscendedTransaction` and `_SqliteTransaction`: `shop_bought(owner: str, rotation: int) -> dict[int, int]`, `add_shop_purchase(owner: str, rotation: int, slot: int) -> None`, `prune_shop(owner: str, rotation: int) -> None` (deletes this owner's rows with a smaller rotation).
- `delete_player_data` also deletes the owner's `shop_purchases` rows.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ascension/test_repository.py` (it has a `db_path` fixture and imports `SqliteAscendedRepository`, `asyncio` or a `run` helper; follow the file's existing style for running coroutines):

```python
def test_shop_purchases_are_counted_per_slot_and_pruned(db_path):
    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            await tx.create_player("ann", 1.0)
            await tx.add_shop_purchase("ann", 5, 0)
            await tx.add_shop_purchase("ann", 5, 0)
            await tx.add_shop_purchase("ann", 5, 2)
            await tx.add_shop_purchase("ann", 4, 1)
            before = await tx.shop_bought("ann", 5)
            await tx.prune_shop("ann", 5)
            old = await tx.shop_bought("ann", 4)
            await tx.delete_player_data("ann")
            gone = await tx.shop_bought("ann", 5)
        await repo.close()
        return before, old, gone

    before, old, gone = asyncio.run(scenario())
    assert before == {0: 2, 2: 1} and old == {} and gone == {}


def test_a_version_2_database_is_upgraded_to_3(db_path):
    import sqlite3

    from src.ascension.repository import SCHEMA

    legacy = SCHEMA.split("CREATE TABLE shop_purchases")[0]
    conn = sqlite3.connect(str(db_path))
    conn.executescript(f"{legacy} PRAGMA user_version = 2;")
    conn.execute("INSERT INTO players (owner, insignia, created_at) VALUES ('ann', 7, 1.0)")
    conn.commit()
    conn.close()

    async def scenario():
        repo = SqliteAscendedRepository(db_path)
        async with repo.transaction() as tx:
            player = await tx.get_player("ann")
            await tx.add_shop_purchase("ann", 1, 0)
            bought = await tx.shop_bought("ann", 1)
        await repo.close()
        return player, bought

    player, bought = asyncio.run(scenario())
    check = sqlite3.connect(str(db_path))
    version = check.execute("PRAGMA user_version").fetchone()[0]
    check.close()
    assert player.insignia == 7 and bought == {0: 1} and version == 3
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_repository.py -q -k "shop_purchases or version_2"`
Expected: FAIL.

- [ ] **Step 2: Implement**

In `repository.py`:

1. Change `SCHEMA_VERSION = 2` to `SCHEMA_VERSION = 3`.
2. Append the table to `SCHEMA` (before the closing `"""`), keeping it as its own constant so the upgrade can reuse it. Replace the end of `SCHEMA` so the last statement is followed by `SHOP_SCHEMA`:

```python
SHOP_SCHEMA = """
CREATE TABLE shop_purchases (
    owner TEXT NOT NULL, rotation INTEGER NOT NULL, slot INTEGER NOT NULL, bought INTEGER NOT NULL CHECK (bought >= 0),
    PRIMARY KEY (owner, rotation, slot));
"""
```

and change the schema creation line to use `SCHEMA + SHOP_SCHEMA`. To keep the test above simple, define `SCHEMA` so that it contains the shop table text last: write `SCHEMA = BASE_SCHEMA + SHOP_SCHEMA` where `BASE_SCHEMA` is the existing text, and in the test split on `"CREATE TABLE shop_purchases"`.

3. In `_open`, replace the version branch:

```python
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                conn.executescript(f"BEGIN; {SCHEMA} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
            elif version == 2:
                conn.executescript(f"BEGIN; {SHOP_SCHEMA} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(f"database schema version {version} is not supported (expected {SCHEMA_VERSION})")
```

4. Add to the `AscendedTransaction` protocol:

```python
    async def shop_bought(self, owner: str, rotation: int) -> dict[int, int]: ...
    async def add_shop_purchase(self, owner: str, rotation: int, slot: int) -> None: ...
    async def prune_shop(self, owner: str, rotation: int) -> None: ...
```

5. Add to `_SqliteTransaction` (before `delete_player_data`):

```python
    # -- rotating shop ---------------------------------------------------------------

    async def shop_bought(self, owner: str, rotation: int) -> dict[int, int]:
        rows = await self._run("SELECT slot, bought FROM shop_purchases WHERE owner = ? AND rotation = ?", (owner, rotation), "all")
        return {row["slot"]: row["bought"] for row in rows}

    async def add_shop_purchase(self, owner: str, rotation: int, slot: int) -> None:
        await self._run(
            "INSERT INTO shop_purchases (owner, rotation, slot, bought) VALUES (?, ?, ?, 1) "
            "ON CONFLICT (owner, rotation, slot) DO UPDATE SET bought = bought + 1",
            (owner, rotation, slot),
        )

    async def prune_shop(self, owner: str, rotation: int) -> None:
        await self._run("DELETE FROM shop_purchases WHERE owner = ? AND rotation < ?", (owner, rotation))
```

6. In `delete_player_data`, add `await self._run("DELETE FROM shop_purchases WHERE owner = ?", (owner,))` before the `players` delete.

- [ ] **Step 3: Run**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_repository.py tests/ascension/test_repository_hardening.py tests/ascension/test_reset.py -q`
Expected: PASS. If a hardening test asserts the exact SQL of the version check or counts statements, adjust it to the new branch without weakening it.

### Task 3: `ShopService` offers (list and buy)

**Files:**
- Modify: `apps/ascension/src/ascension/errors.py` (add `SoldOut`)
- Modify: `apps/ascension/src/ascension/shop.py`
- Modify: `apps/ascension/src/ascension/composition.py`
- Modify: `apps/ascension/tests/ascension/env.py`, `apps/ascension/tests/ascension/test_shop.py`

**Interfaces:**
- Consumes: `ShopOffers.window`, repository shop counters (Tasks 1 and 2).
- Produces: `ShopService(repository, writer, catalog, progression, offers, clock)`; `await shop.list_offers(owner) -> dict` with keys `rotation`, `refreshes_at`, `seconds_left`, `offers`; `await shop.buy_offer(owner, key, rotation, slot) -> dict` with keys `kind="copies"`, `ascended_id`, `tier_id`, `copies_granted`, `price`, `resulting_tier_id`, `slot`, `rotation`, `left`. `buy_copies` is removed.
- `Env(db_path, rng=None, offers=None)`; `env.shop` uses `offers or ShopOffers(CATALOG, 21600.0, 5)`.

- [ ] **Step 1: Add the error**

In `errors.py`:

```python
class SoldOut(Conflict):
    """The offer's stock for this rotation is used up."""
```

- [ ] **Step 2: Update `Env`**

In `tests/ascension/env.py` change the signature to `def __init__(self, db_path: Path, rng: RandomSource | None = None, offers=None) -> None:`, import `ShopOffers` from `src.ascension.shop_offers`, and replace the shop line with:

```python
        self.offers = offers or ShopOffers(CATALOG, 21600.0, 5)
        self.shop = ShopService(self.repo, self.writer, CATALOG, self.progression, self.offers, self.clock)
```

- [ ] **Step 3: Write the failing tests**

In `tests/ascension/test_shop.py`: delete the tests that call `env.shop.buy_copies` (the Ascended-copies tests around lines 76 to 120, the cooldown-free part of the "fighting" test, and the line `await env.shop.buy_copies("ann", "c2", "scout", "common")`), and change `_price` to `ShopService(None, None, CATALOG, None, None, None).copy_price(...)`. Add the following tests (imports: `Offer` from `src.ascension.shop_offers`, `FixedOffers` from `tests.ascension.helpers`, `SoldOut` and `Conflict` from `src.ascension.errors`):

```python
def fixed(*offers):
    return lambda tmp: Env(tmp / "s.sqlite3", offers=FixedOffers(*offers))


GUARDIAN_COMMON = Offer(0, "guardian", "common", 2)
SCOUT_RARE = Offer(1, "scout", "rare", 1)


def test_the_window_lists_offers_with_the_servers_price(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON, SCOUT_RARE)(tmp_path)
        await env.start_player()
        window = await env.shop.list_offers("ann")
        await env.close()
        return env, window

    env, window = run(scenario())
    assert window["rotation"] == int(env.clock.now() // 21600.0)
    assert window["seconds_left"] == window["refreshes_at"] - env.clock.now()
    first, second = window["offers"]
    owned = AscendedRecord("ann", "guardian", 0, 1, 0)
    price, granted, resulting = _price(owned, "common")
    assert (first["slot"], first["ascended_id"], first["tier_id"]) == (0, "guardian", "common")
    assert (first["price"], first["copies_granted"], first["resulting_tier_id"]) == (price, granted, resulting)
    assert first["stock"] == 2 and first["left"] == 2 and second["left"] == 1
    assert "owned_copies" in first


def test_buying_an_offer_grants_copies_and_uses_stock(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON)(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        first = await env.shop.buy_offer("ann", "b1", rotation, 0)
        second = await env.shop.buy_offer("ann", "b2", rotation, 0)
        with pytest.raises(SoldOut):
            await env.shop.buy_offer("ann", "b3", rotation, 0)
        window = await env.shop.list_offers("ann")
        insignia, _ = await balance(env)
        await env.close()
        return first, second, window, insignia

    first, second, window, insignia = run(scenario())
    assert first["kind"] == "copies" and first["left"] == 1 and second["left"] == 0
    assert window["offers"][0]["left"] == 0
    assert insignia == 1000 - first["price"] - second["price"]


def test_a_stale_rotation_and_an_unknown_slot_are_refused(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON)(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        with pytest.raises(Conflict, match="refreshed"):
            await env.shop.buy_offer("ann", "b1", rotation - 1, 0)
        with pytest.raises(InvalidRequest):
            await env.shop.buy_offer("ann", "b2", rotation, 9)
        with pytest.raises(InvalidRequest):
            await env.shop.buy_offer("ann", "b3", rotation, True)
        env.clock.advance(21600)
        with pytest.raises(Conflict, match="refreshed"):
            await env.shop.buy_offer("ann", "b4", rotation, 0)
        await env.close()

    run(scenario())


def test_a_new_rotation_restores_stock_and_drops_old_counts(tmp_path):
    async def scenario():
        env = fixed(Offer(0, "guardian", "common", 1))(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        first_rotation = env.offers.rotation_at(env.clock.now())
        await env.shop.buy_offer("ann", "b1", first_rotation, 0)
        env.clock.advance(21600)
        second_rotation = env.offers.rotation_at(env.clock.now())
        again = await env.shop.buy_offer("ann", "b2", second_rotation, 0)
        async with env.repo.transaction() as tx:
            old = await tx.shop_bought("ann", first_rotation)
        await env.close()
        return again, old

    again, old = run(scenario())
    assert again["left"] == 0 and old == {}


def test_a_fighting_ascended_cannot_be_bought_but_others_can(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON, SCOUT_RARE)(tmp_path)
        await env.start_player()
        await env.give(insignia=5000, guardian=AscendedRecord("ann", "guardian", 3, 1, 0))
        async with env.repo.transaction() as tx:
            await tx.add_battle(battle_record())
        rotation = env.offers.rotation_at(env.clock.now())
        with pytest.raises(WrongPhase):
            await env.shop.buy_offer("ann", "b1", rotation, 0)
        await env.shop.buy_offer("ann", "b2", rotation, 1)
        await env.close()

    run(scenario())


def test_a_retried_offer_purchase_is_charged_once(tmp_path):
    async def scenario():
        env = fixed(GUARDIAN_COMMON)(tmp_path)
        await env.start_player()
        await env.give(insignia=1000)
        rotation = env.offers.rotation_at(env.clock.now())
        first = await env.shop.buy_offer("ann", "same", rotation, 0)
        second = await env.shop.buy_offer("ann", "same", rotation, 0)
        insignia, _ = await balance(env)
        await env.close()
        return first, second, insignia

    first, second, insignia = run(scenario())
    assert first == second and insignia == 1000 - first["price"]


def test_not_enough_insignia_keeps_the_stock(tmp_path):
    async def scenario():
        env = fixed(SCOUT_RARE)(tmp_path)
        await env.start_player()
        rotation = env.offers.rotation_at(env.clock.now())
        with pytest.raises(InsufficientFunds):
            await env.shop.buy_offer("ann", "b1", rotation, 0)
        window = await env.shop.list_offers("ann")
        await env.close()
        return window

    assert run(scenario())["offers"][0]["left"] == 1
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_shop.py -q`
Expected: FAIL.

- [ ] **Step 4: Implement `ShopService`**

In `shop.py`: change the imports to include `Conflict, SoldOut` from errors, `ShopOffers`/`Offer` types, `AscendedRepository` from the repository, and `Clock` from runtime. Replace `__init__` and `buy_copies`:

```python
class ShopService:
    def __init__(self, repository: AscendedRepository, writer: IdempotentWriter, catalog: Catalog,
                 progression: ProgressionService, offers: ShopOffers, clock: Clock) -> None:
        self._repository, self._writer, self._catalog = repository, writer, catalog
        self._progression, self._offers, self._clock = progression, offers, clock
```

Remove `buy_copies`. Add:

```python
    async def list_offers(self, owner: str) -> dict[str, Any]:
        """This account's current window: each offer with its remaining stock and today's price."""
        now = self._clock.now()
        window = self._offers.window(owner, now)
        async with self._repository.transaction() as tx:
            if await tx.get_player(owner) is None:
                raise NotFound("no profile yet; choose a starter first")
            bought = await tx.shop_bought(owner, window.rotation)
            owned = {record.ascended_id: record for record in await tx.list_ascendeds(owner)}
        offers = []
        for offer in window.offers:
            record = owned.get(offer.ascended_id)
            price, granted, resulting = self.copy_price(offer.ascended_id, record, offer.tier_id)
            offers.append({
                "slot": offer.slot, "ascended_id": offer.ascended_id, "tier_id": offer.tier_id,
                "copies_granted": granted, "stock": offer.stock, "left": max(0, offer.stock - bought.get(offer.slot, 0)),
                "price": price, "resulting_tier_id": resulting, "owned_copies": record.copies if record else 0,
            })
        return {"rotation": window.rotation, "refreshes_at": window.refreshes_at,
                "seconds_left": max(0.0, window.refreshes_at - now), "offers": offers}

    async def buy_offer(self, owner: str, key: str, rotation: int, slot: int) -> dict[str, Any]:
        for value in (rotation, slot):
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidRequest("rotation and slot must be whole numbers")

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            window = self._offers.window(owner, self._clock.now())
            if rotation != window.rotation:
                raise Conflict("the shop has refreshed; look at the new offers")
            offer = next((o for o in window.offers if o.slot == slot), None)
            if offer is None:
                raise InvalidRequest("there is no such offer")
            bought = (await tx.shop_bought(owner, rotation)).get(slot, 0)
            if bought >= offer.stock:
                raise SoldOut("that offer is sold out")
            await self._reject_if_fighting(tx, owner, offer.ascended_id)
            owned = await tx.get_ascended(owner, offer.ascended_id)
            price, granted, resulting = self.copy_price(offer.ascended_id, owned, offer.tier_id)
            await self._spend(tx, owner, price)
            if owned is None:
                await tx.put_ascended(AscendedRecord(owner, offer.ascended_id, granted, 1, 0))
            else:
                await tx.put_ascended(replace(owned, copies=owned.copies + granted))
            await tx.add_shop_purchase(owner, rotation, slot)
            await tx.prune_shop(owner, rotation)
            return {"kind": "copies", "ascended_id": offer.ascended_id, "tier_id": offer.tier_id, "copies_granted": granted,
                    "price": price, "resulting_tier_id": resulting, "slot": slot, "rotation": rotation,
                    "left": offer.stock - bought - 1}

        return await self._writer.commit(owner, key, "shop.offer", {"rotation": rotation, "slot": slot}, work)
```

`InvalidRequest` is already imported; add `Conflict, SoldOut`. Update the module docstring first line to mention the rotating offers.

- [ ] **Step 5: Wire composition**

In `composition.py` add `from src.ascension.shop_offers import ShopOffers`, then replace the shop line with:

```python
        shop=ShopService(repository, writer, catalog, progression, ShopOffers(catalog, config.shop_rotation_seconds, config.shop_offers), clock),
```

(`config.shop_rotation_seconds` and `config.shop_offers` arrive in Task 4; until then run only `test_shop.py` and add the two fields in Task 4 before the full suite.)

- [ ] **Step 6: Run**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_shop.py tests/ascension/test_shop_offers.py -q`
Expected: PASS.

### Task 4: Config, API and tests

**Files:**
- Modify: `apps/ascension/src/config.py`, `apps/ascension/configs/config_app.json`, `apps/ascension/configs/config_app.json.example`
- Modify: `apps/ascension/src/ascension/api.py`
- Test: `apps/ascension/tests/test_config.py`, `apps/ascension/tests/test_config_validation.py`, `apps/ascension/tests/ascension/test_api.py`

**Interfaces:**
- Consumes: `ShopService.list_offers`, `ShopService.buy_offer`.
- Produces: `AppConfig.shop_rotation_seconds: float` (at least 60), `AppConfig.shop_offers: int` (1 to 12); `GET /ascension/shop`; `POST /ascension/shop/purchases` with `{"kind": "copies", "rotation": int, "slot": int}`.

- [ ] **Step 1: Config**

In `src/config.py` add `shop_rotation_seconds: float` and `shop_offers: int` to `AppConfig` (after `faint_seconds`) and in `parse_config`:

```python
        shop_rotation_seconds=_number(raw, "shop_rotation_seconds", float, 60.0),
        shop_offers=_number(raw, "shop_offers", int, 1, 12),
```

Add `"shop_rotation_seconds": 21600.0, "shop_offers": 5` (after `faint_seconds`) to both `configs/config_app.json` and `configs/config_app.json.example`. This is the user-allowed local config; keep the other keys unchanged.

- [ ] **Step 2: Config tests**

In `tests/test_config_validation.py` add `"shop_rotation_seconds"` and `"shop_offers"` to the parametrised `key` list used for missing/invalid values (line 18). In `tests/test_config.py`, add to the test that checks loaded values:

```python
    assert config.shop_rotation_seconds == 21600.0 and config.shop_offers == 5
```

Also add a test that `shop_offers` of 0 and 13 and `shop_rotation_seconds` of 10 raise `ConfigError` (copy the shape of the neighbouring bound tests).

Run: `.venv_ascension\Scripts\python -m pytest tests/test_config.py tests/test_config_validation.py -q`
Expected: PASS.

- [ ] **Step 3: Write the failing API tests**

In `tests/ascension/test_api.py` replace the copies line in `test_shop_over_http` (line 217: the `ascended_id`/`tier` request expecting 409) with:

```python
    assert client.post("/ascension/shop/purchases", json={"kind": "copies", "ascended_id": "sentinel", "tier": "common"}, headers=headers(client, )).status_code == 422
    assert client.post("/ascension/shop/purchases", json={"kind": "copies"}, headers=headers(client, )).status_code == 400
```

and append:

```python
def test_the_shop_lists_offers_and_sells_one(client):
    start_profile(client)
    shop = client.get("/ascension/shop", headers=headers(client, key=False))
    assert shop.status_code == 200, shop.text
    body = shop.json()
    assert len(body["offers"]) == 5 and body["seconds_left"] > 0
    offer = body["offers"][0]
    poor = client.post("/ascension/shop/purchases", json={"kind": "copies", "rotation": body["rotation"], "slot": offer["slot"]}, headers=headers(client))
    assert poor.status_code == 409  # a new player has no Insignia


def test_a_stale_rotation_and_a_missing_slot_are_refused_over_http(client):
    start_profile(client)
    body = client.get("/ascension/shop", headers=headers(client, key=False)).json()
    stale = client.post("/ascension/shop/purchases", json={"kind": "copies", "rotation": body["rotation"] - 1, "slot": 0}, headers=headers(client))
    assert stale.status_code == 409 and "refreshed" in stale.json()["error"]
    missing = client.post("/ascension/shop/purchases", json={"kind": "copies", "rotation": body["rotation"], "slot": 99}, headers=headers(client))
    assert missing.status_code == 400


def test_the_shop_needs_a_profile(client):
    assert client.get("/ascension/shop", headers=headers(client, "newbie", key=False)).status_code == 404
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_api.py -q -k "shop"`
Expected: FAIL.

- [ ] **Step 4: Implement the API**

In `api.py` change `PurchaseBody`:

```python
class PurchaseBody(_Body):
    kind: str
    tier: str | None = None
    quantity: StrictInt = 1
    rotation: StrictInt | None = None
    slot: StrictInt | None = None
```

Replace the purchase route and add the shop route (place `GET /shop` above it):

```python
    @router.get("/shop")
    async def shop_window(owner: str = Depends(requester)):
        return await shop.list_offers(owner)

    @router.post("/shop/purchases", status_code=201)
    async def purchase(body: PurchaseBody, owner: str = Depends(requester), key: str = Depends(idempotency_key)):
        if body.kind == "emblem" and body.tier:
            return await shop.buy_emblems(owner, key, body.tier, body.quantity)
        if body.kind == "copies" and body.rotation is not None and body.slot is not None:
            return await shop.buy_offer(owner, key, body.rotation, body.slot)
        raise HTTPException(400, 'kind must be "emblem" (with tier, quantity) or "copies" (with rotation, slot)')
```

- [ ] **Step 5: Run the whole backend suite**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: PASS (all prior tests plus the new ones). Fix any other test that built `ShopService(...)` or an `AppConfig(...)` by hand.

### Task 5: Backend docs and phase check

**Files:**
- Modify: `apps/ascension/README.md`

- [ ] **Step 1: README**

Add `| GET /ascension/shop | This account's current offers: rotation, seconds left, and per offer slot, Ascended, tier, stock, left, price |` to the endpoint table (line 142 area), change the purchases row to `Buy EMBLEMs ({kind: "emblem", tier, quantity}) or an offer ({kind: "copies", rotation, slot})`, and add a short "Rotating shop" paragraph (rotation period, 5 offers, stock by tier, per account, config keys `shop_rotation_seconds` and `shop_offers`, database version 3 upgrade). Add the two config keys to the config table if the README has one.

- [ ] **Step 2: Commit boundary 1 (only when the user says "commit")**

```bash
git add apps/ascension/src apps/ascension/tests apps/ascension/configs/ascension_catalog.json apps/ascension/configs/config_app.json.example apps/ascension/README.md
git commit -m "feat: Ascension shop rotates limited copy offers every 6 hours"
```

(`configs/config_app.json` is the local copy; stage it only if it is tracked.)

---

## Phase B: Web (commit 2)

### Task 6: Client types, store state and countdown

**Files:**
- Modify: `apps/ascension/web/src/api/AscensionClient.ts`
- Modify: `apps/ascension/web/src/api/AscensionClient.fixtures.ts`
- Modify: `apps/ascension/web/src/stores/ascension.ts`
- Test: `apps/ascension/web/src/stores/ascension.test.ts`, `apps/ascension/web/src/api/AscensionClient.test.ts` (if present; otherwise skip)

**Interfaces:**
- Produces types: `ShopOffer { slot; ascended_id; tier_id; copies_granted; stock; left; price; resulting_tier_id; owned_copies }`, `ShopWindow { rotation; refreshes_at; seconds_left; offers: ShopOffer[] }`; `CopyPurchase` gains `slot`, `rotation`, `left`.
- Produces client: `shop()`, `buyOffer(rotation, slot, key?)`; removes `buyCopies`.
- Produces store: `shop: Ref<ShopWindow | null>`, `shopEndsAt: Ref<number>` (device epoch seconds, `Date.now() / 1000 + seconds_left` at receipt), `loadShop(): Promise<void>`, `buyOffer(offer: ShopOffer): Promise<CopyPurchase | null>`; removes `buyCopies`.

- [ ] **Step 1: Client**

In `AscensionClient.ts` replace the `CopyPurchase` interface and add:

```ts
export interface CopyPurchase {
  kind: "copies";
  ascended_id: string;
  tier_id: string;
  copies_granted: number;
  price: number;
  resulting_tier_id: string;
  slot: number;
  rotation: number;
  left: number;
}

export interface ShopOffer {
  slot: number;
  ascended_id: string;
  tier_id: string;
  copies_granted: number;
  stock: number;
  left: number;
  price: number;
  resulting_tier_id: string;
  owned_copies: number;
}

export interface ShopWindow {
  rotation: number;
  refreshes_at: number;
  /** Seconds to the next rotation when the answer was made; count down on this device's clock. */
  seconds_left: number;
  offers: ShopOffer[];
}
```

Replace the `buyCopies` member with:

```ts
  shop = () => this.http.request<ShopWindow>("GET", `${BASE}/shop`);
  buyOffer = (rotation: number, slot: number, key: string = newIdempotencyKey()) =>
    this.http.request<CopyPurchase>("POST", `${BASE}/shop/purchases`, { kind: "copies", rotation, slot }, withKey(key));
```

Match how other GET members call `http.request` in this file (e.g. `profile`); copy that exact form if it differs.

- [ ] **Step 2: Fixtures**

In `AscensionClient.fixtures.ts` add (export):

```ts
export function shopOffer(extra: Partial<ShopOffer> = {}): ShopOffer {
  return {
    slot: 0, ascended_id: "guardian", tier_id: "common", copies_granted: 1, stock: 3, left: 3,
    price: 40, resulting_tier_id: "common", owned_copies: 0, ...extra,
  };
}

export function shopWindow(extra: Partial<ShopWindow> = {}): ShopWindow {
  return {
    rotation: 46, refreshes_at: 1_015_200, seconds_left: 3600,
    offers: [shopOffer(), shopOffer({ slot: 1, ascended_id: "scout", tier_id: "rare", stock: 1, left: 1, price: 90 })],
    ...extra,
  };
}
```

and import `ShopOffer, ShopWindow` from `./AscensionClient` (type imports; follow the file's current import style).

- [ ] **Step 3: Write the failing store tests**

In `stores/ascension.test.ts`, add `shop: vi.fn(), buyOffer: vi.fn(),` to the mocked `client` object and replace `buyCopies: vi.fn(),` with nothing. Add (using the file's existing helpers for creating an attached store with a profile; mirror an existing purchase test such as the one for `buyEmblems`):

```ts
describe("rotating shop", () => {
  it("loads the window and counts down from the answer on this device's clock", async () => {
    client.shop.mockResolvedValue(shopWindow({ seconds_left: 120 }));
    const store = useAscensionStore();
    const before = Date.now() / 1000;

    await store.loadShop();

    expect(store.shop?.offers).toHaveLength(2);
    expect(store.shopEndsAt).toBeGreaterThanOrEqual(before + 120);
    expect(store.shopEndsAt).toBeLessThan(before + 125);
  });

  it("buys an offer, then reloads the window and the profile", async () => {
    client.shop.mockResolvedValue(shopWindow());
    client.buyOffer.mockResolvedValue({ kind: "copies", ascended_id: "guardian", tier_id: "common", copies_granted: 1, price: 40, resulting_tier_id: "common", slot: 0, rotation: 46, left: 2 });
    client.profile.mockResolvedValue(PROFILE);
    const store = useAscensionStore();
    await store.loadShop();

    const bought = await store.buyOffer(store.shop!.offers[0]!);

    expect(client.buyOffer).toHaveBeenCalledWith(46, 0);
    expect(bought?.left).toBe(2);
    expect(client.shop).toHaveBeenCalledTimes(2);
  });

  it("reloads the window when the shop says it has refreshed", async () => {
    client.shop.mockResolvedValue(shopWindow());
    client.buyOffer.mockRejectedValue(new ApiError(409, "the shop has refreshed; look at the new offers"));
    const store = useAscensionStore();
    await store.loadShop();

    await store.buyOffer(store.shop!.offers[0]!);

    expect(store.error).toBe("the shop has refreshed; look at the new offers");
    expect(client.shop).toHaveBeenCalledTimes(2);
  });
});
```

Add `shopWindow` to the fixtures import. Run: `npx vitest run src/stores/ascension.test.ts` from `apps/ascension/web`. Expected: FAIL.

- [ ] **Step 4: Implement in the store**

In `stores/ascension.ts` add `type ShopWindow, type ShopOffer` to the client type imports and:

```ts
  /** The account's current shop window and, on this device's clock, when it ends. */
  const shop = ref<ShopWindow | null>(null);
  const shopEndsAt = ref(0);

  async function loadShop(): Promise<void> {
    const started = generation;
    try {
      const window = await ascensionClient.shop();
      if (started !== generation) return;
      shop.value = window;
      shopEndsAt.value = Date.now() / 1000 + window.seconds_left;
    } catch (err) {
      if (started === generation) report(err);
    }
  }

  async function buyOffer(offer: ShopOffer): Promise<CopyPurchase | null> {
    const current = shop.value;
    if (current === null) return null;
    const result = await mutate(
      () => ascensionClient.buyOffer(current.rotation, offer.slot),
      () => refreshProfile(),
    );
    // A refresh, a sold-out offer or a purchase all change what the shop shows.
    await loadShop();
    return result;
  }
```

Remove `buyCopies`; return `shop, shopEndsAt, loadShop, buyOffer` from the store instead of `buyCopies`. In the `session.revision` watcher (account change) and wherever `profile.value = null` resets run, also set `shop.value = null`.

Run the store tests. Expected: PASS.

### Task 7: Shared hover lift and the shop cards

**Files:**
- Modify: `apps/ascension/web/src/components/theme.css`
- Modify: `apps/ascension/web/src/components/ShopPanel.vue` (rewrite)
- Modify: `apps/ascension/web/src/components/ShopPanel.test.ts`

**Interfaces:**
- Consumes: store `shop`, `shopEndsAt`, `loadShop`, `buyOffer`; fixtures `shopWindow`, `shopOffer`; `useNowSeconds`; `formatCountdown`.
- Produces: the global class `.em-lift` (used by Task 8).

- [ ] **Step 1: `.em-lift` in `theme.css`**

Append:

```css
/* A card that answers the pointer: it rises a little and its edge brightens. A card with a
 * tier colour (--tier) glows in it. Disabled and sold-out cards do not lift. */
.em-lift {
  transition: transform 160ms ease-out, box-shadow 160ms ease-out, border-color 160ms ease-out;
}
.em-lift:not(.is-off):hover,
.em-lift:not(.is-off):focus-within {
  transform: translateY(-4px) scale(1.02);
  border-color: var(--tier, var(--em-accent));
  box-shadow: 0 10px 22px #0008, 0 0 14px color-mix(in srgb, var(--tier, var(--em-accent)) 35%, transparent);
}
@media (prefers-reduced-motion: reduce) {
  .em-lift {
    transition: none;
  }
  .em-lift:not(.is-off):hover,
  .em-lift:not(.is-off):focus-within {
    transform: none;
  }
}
```

- [ ] **Step 2: Write the failing shop tests**

In `ShopPanel.test.ts`: add `shop: vi.fn(), buyOffer: vi.fn()` to the mocked client, remove `buyCopies`, import `shopWindow, shopOffer` from the fixtures, and make `mountShop` set `store.shop = shopWindow(); store.shopEndsAt = Date.now() / 1000 + 3 * 3600 + 12 * 60;` and mock `client.shop.mockResolvedValue(shopWindow())` in `beforeEach`. Replace the copy-price test and keep the EMBLEM and sell tests (they use `[data-tier]` and `[data-sell]`, so the EMBLEM cards and sell cards must keep those attributes and their first `button`/`input`). Add:

```ts
  it("shows the offers with stock, price and the time to the next rotation", () => {
    const { wrapper } = mountShop(500);

    const cards = wrapper.findAll("[data-offer]");
    expect(cards).toHaveLength(2);
    expect(cards[0]!.text()).toContain("Guardian");
    expect(cards[0]!.text()).toContain("3 left");
    expect(cards[0]!.text()).toContain("40");
    expect(cards[1]!.text()).toContain("1 left");
    expect(wrapper.find(".refresh").text()).toContain("Refreshes in 3:12:00");
  });

  it("buys an offer and says what it bought", async () => {
    client.buyOffer.mockResolvedValue({ kind: "copies", ascended_id: "guardian", tier_id: "common", copies_granted: 1, price: 40, resulting_tier_id: "common", slot: 0, rotation: 46, left: 2 });
    const { wrapper } = mountShop(500);

    await wrapper.find('[data-offer="0"] button').trigger("click");
    await flushPromises();

    expect(client.buyOffer).toHaveBeenCalledExactlyOnceWith(46, 0);
    expect(wrapper.find(".notice").text()).toBe("Bought 1 copy of Guardian for 40 Insignia; it is now Common.");
  });

  it("marks a sold-out offer and an unaffordable one", () => {
    const { store, wrapper } = mountShop(50);
    store.shop = shopWindow({ offers: [shopOffer({ left: 0 }), shopOffer({ slot: 1, ascended_id: "scout", price: 90 })] });

    return wrapper.vm.$nextTick().then(() => {
      const [soldOut, dear] = wrapper.findAll("[data-offer]");
      expect(soldOut!.classes()).toContain("is-off");
      expect(soldOut!.text()).toContain("Sold out");
      expect(soldOut!.find("button").attributes("disabled")).toBeDefined();
      expect(dear!.classes()).toContain("is-off");
      expect(dear!.find("button").attributes("disabled")).toBeDefined();
    });
  });

  it("loads the window when the tab opens", () => {
    mountShop(500);

    expect(client.shop).toHaveBeenCalled();
  });
```

Run: `npx vitest run src/components/ShopPanel.test.ts`. Expected: FAIL.

- [ ] **Step 3: Rewrite `ShopPanel.vue`**

Replace the file with this (keep the EMBLEM and sell behaviour; the EMBLEM quantity logic and sell dialog are unchanged):

```vue
<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { ShopOffer } from "../api/AscensionClient";
import { useNowSeconds } from "../composables/useNowSeconds";
import { useAscensionStore } from "../stores/ascension";
import { formatCountdown, titleCase } from "../utils/ascension";
import { ascendedArt } from "./ascendedArt";
import EmButton from "./ui/EmButton.vue";
import EmConfirm from "./ui/EmConfirm.vue";
import EmIcon from "./ui/EmIcon.vue";
import EmPanel from "./ui/EmPanel.vue";
import EmTierBadge from "./ui/EmTierBadge.vue";

/** The Shop tab: the wallet, this account's rotating copy offers (each with limited stock, new
 * ones every few hours), EMBLEMs per tier, and selling one absorbed copy. A card that cannot be
 * bought (sold out, or Insignia would not cover it) is dimmed and does not lift. A copy's price
 * comes from the server, which also refuses when Insignia falls short; the page shows that
 * message (the store's `error`). */
const store = useAscensionStore();
const MAX_QUANTITY = 99;

const insignia = computed(() => store.profile?.insignia ?? 0);
const tiers = computed(() => store.catalog?.tiers ?? []);
const quantities = reactive<Record<string, number>>({});
const message = ref("");
const outOfReach = computed(() => tiers.value.filter((t) => t.emblem_price > insignia.value).map((t) => titleCase(t.id)));

const now = useNowSeconds();
const secondsLeft = computed(() => Math.max(0, store.shopEndsAt - now.value));
const offers = computed(() => store.shop?.offers ?? []);
const nameOf = (id: string) => store.catalog?.ascendeds.find((a) => a.id === id)?.name ?? titleCase(id);
const artOf = (id: string) => ascendedArt(id)?.url ?? null;

onMounted(() => void store.loadShop());
// At zero a new rotation has begun: ask for it.
watch(
  () => secondsLeft.value <= 0 && store.shop !== null,
  (over) => {
    if (over) void store.loadShop();
  },
);

function offerOff(offer: ShopOffer): boolean {
  return offer.left <= 0 || offer.price > insignia.value;
}

async function buyOffer(offer: ShopOffer): Promise<void> {
  message.value = "";
  const bought = await store.buyOffer(offer);
  if (bought) {
    const copies = `${bought.copies_granted} ${bought.copies_granted === 1 ? "copy" : "copies"}`;
    message.value = `Bought ${copies} of ${nameOf(bought.ascended_id)} for ${bought.price} Insignia; it is now ${titleCase(bought.resulting_tier_id)}.`;
  }
}

function quantityOf(tierId: string): number {
  return quantities[tierId] ?? 1;
}

function emblemCost(tierId: string, price: number): number {
  return price * quantityOf(tierId);
}

function canBuyEmblems(tierId: string, price: number): boolean {
  const quantity = quantityOf(tierId);
  const valid = Number.isInteger(quantity) && quantity >= 1 && quantity <= MAX_QUANTITY;
  return !store.busy && valid && emblemCost(tierId, price) <= insignia.value;
}

function setQuantity(tierId: string, event: Event): void {
  quantities[tierId] = Number((event.target as HTMLInputElement).value);
}

async function buyEmblems(tierId: string): Promise<void> {
  message.value = "";
  const bought = await store.buyEmblems(tierId, quantityOf(tierId));
  if (bought) {
    message.value = `Bought ${bought.quantity} ${titleCase(bought.tier_id)} EMBLEM${bought.quantity === 1 ? "" : "s"} for ${bought.price} Insignia.`;
  }
}

const sellable = computed(() => (store.profile?.ascendeds ?? []).filter((s) => s.copies > 0));
const selling = ref<string | null>(null);
const sellingName = computed(() => sellable.value.find((s) => s.ascended_id === selling.value)?.name ?? "");

async function sell(): Promise<void> {
  const ascendedId = selling.value;
  selling.value = null;
  if (ascendedId === null) return;
  message.value = "";
  const sale = await store.sellCopy(ascendedId);
  if (sale) {
    message.value = `Sold one copy for ${sale.value} Insignia${sale.downgraded ? `; it is now ${titleCase(sale.tier_id)}` : ""}.`;
  }
}
</script>

<template>
  <section class="shop">
    <p v-if="message" class="notice" role="status"><EmIcon name="check" /> {{ message }}</p>

    <EmPanel class="wallet">
      <div class="balance">
        <p class="em-eyebrow">Your wallet</p>
        <h3 class="em-pixel em-num amount">{{ insignia }} Insignia</h3>
      </div>
      <div v-for="t in tiers" :key="t.id" class="count" :style="{ '--tier': `var(--em-tier-${t.id}, var(--em-tier-common))` }">
        <strong class="em-pixel em-num">{{ store.profile?.emblems[t.id] ?? 0 }}</strong>
        <span>{{ titleCase(t.id) }} EMBLEMs</span>
      </div>
    </EmPanel>

    <EmPanel>
      <div class="section-head">
        <h3 class="em-pixel">Today's offers</h3>
        <small class="refresh em-num">Refreshes in {{ formatCountdown(secondsLeft) }}</small>
      </div>
      <p v-if="store.shop && offers.length === 0" class="empty">Nothing is on offer right now.</p>
      <ul v-else class="cards">
        <li
          v-for="offer in offers"
          :key="offer.slot"
          class="card em-lift"
          :class="{ 'is-off': offerOff(offer) }"
          :data-offer="offer.slot"
          :style="{ '--tier': `var(--em-tier-${offer.tier_id}, var(--em-tier-common))` }"
        >
          <span v-if="offer.left <= 0" class="ribbon">Sold out</span>
          <div class="portrait">
            <img v-if="artOf(offer.ascended_id)" :src="artOf(offer.ascended_id)!" alt="" draggable="false" />
            <span v-else class="letter" aria-hidden="true">{{ nameOf(offer.ascended_id).slice(0, 1) }}</span>
          </div>
          <h4>{{ nameOf(offer.ascended_id) }}</h4>
          <div class="meta">
            <EmTierBadge :tier-id="offer.tier_id" />
            <span class="em-num">+{{ offer.copies_granted }} {{ offer.copies_granted === 1 ? "copy" : "copies" }}</span>
          </div>
          <p class="em-num owned">You have {{ offer.owned_copies }} · becomes {{ titleCase(offer.resulting_tier_id) }}</p>
          <p class="em-num stock">{{ offer.left }} left</p>
          <EmButton variant="primary" class="block" :disabled="store.busy || offerOff(offer)" @click="buyOffer(offer)">
            <EmIcon name="shop" /> {{ offer.price }} Insignia
          </EmButton>
        </li>
      </ul>
      <p class="hint">Offers are yours alone and change every few hours. Absorbed copies raise an Ascended's tier.</p>
    </EmPanel>

    <EmPanel>
      <div class="section-head">
        <h3 class="em-pixel">Buy EMBLEMs</h3>
        <small>Choose how many, then buy</small>
      </div>
      <ul class="cards emblems">
        <li
          v-for="t in tiers"
          :key="t.id"
          class="card em-lift"
          :class="{ 'is-off': t.emblem_price > insignia }"
          :data-tier="t.id"
          :style="{ '--tier': `var(--em-tier-${t.id}, var(--em-tier-common))` }"
        >
          <div class="band" aria-hidden="true" />
          <div class="meta">
            <EmTierBadge :tier-id="t.id" />
            <span>{{ titleCase(t.id) }} EMBLEM</span>
          </div>
          <p class="em-num price"><strong>{{ t.emblem_price }}</strong> Insignia</p>
          <p class="em-num owned">{{ store.profile?.emblems[t.id] ?? 0 }} owned</p>
          <input
            type="number"
            min="1"
            :max="MAX_QUANTITY"
            :value="quantityOf(t.id)"
            :aria-label="`${titleCase(t.id)} EMBLEMs to buy`"
            @input="setQuantity(t.id, $event)"
          />
          <EmButton variant="primary" class="block" :disabled="!canBuyEmblems(t.id, t.emblem_price)" @click="buyEmblems(t.id)">
            Buy for {{ emblemCost(t.id, t.emblem_price) }}
          </EmButton>
        </li>
      </ul>
      <p v-if="outOfReach.length" class="hint">Not enough Insignia for: {{ outOfReach.join(", ") }}.</p>
    </EmPanel>

    <EmPanel>
      <h3 class="em-pixel">Sell an absorbed copy</h3>
      <p v-if="sellable.length === 0" class="empty">No absorbed copies to sell.</p>
      <template v-else>
        <p class="hint">Sell one absorbed copy. Your collected Ascended stays with you.</p>
        <ul class="cards sell">
          <li v-for="s in sellable" :key="s.ascended_id" class="card em-lift" :data-sell="s.ascended_id" :style="{ '--tier': `var(--em-tier-${s.tier_id}, var(--em-tier-common))` }">
            <h4>{{ s.name }}</h4>
            <p class="em-num owned">{{ s.copies }} {{ s.copies === 1 ? "copy" : "copies" }} · {{ titleCase(s.tier_id) }}</p>
            <EmButton class="block" :disabled="store.busy" @click="selling = s.ascended_id"><EmIcon name="coin" /> Sell one copy</EmButton>
          </li>
        </ul>
      </template>
    </EmPanel>

    <EmConfirm
      :open="selling !== null"
      title="Sell one copy?"
      :message="`One absorbed copy of ${sellingName} goes back to the shop for Insignia. Its tier can drop.`"
      confirm-label="Sell"
      :busy="store.busy"
      @confirm="sell"
      @close="selling = null"
    />
  </section>
</template>

<style scoped>
.shop {
  display: flex;
  flex-direction: column;
  gap: var(--em-space-5);
}
.notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: 1px solid var(--em-success);
  border-radius: var(--em-radius);
  color: var(--em-success);
  background: var(--em-success-surface);
}
.wallet {
  display: grid;
  grid-template-columns: 1.5fr repeat(6, 1fr);
  gap: var(--em-space-3);
  align-items: center;
}
.amount {
  margin: 6px 0 0;
  font-size: 18px;
}
.count {
  text-align: center;
  font-size: 12px;
  color: var(--tier);
}
.count strong {
  display: block;
  margin-bottom: 4px;
  font-size: 22px;
  font-weight: 400;
}
.section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--em-space-3);
  margin-bottom: var(--em-space-3);
}
h3 {
  margin: 0 0 var(--em-space-3);
  font-size: 18px;
  line-height: 1.4;
}
.section-head h3 {
  margin: 0;
}
.section-head small {
  color: var(--em-muted);
}
.refresh {
  color: var(--em-accent);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: var(--em-space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--em-space-2);
  padding: var(--em-space-4);
  border: 1px solid var(--em-border);
  border-top: 3px solid var(--tier, var(--em-border));
  border-radius: var(--em-radius);
  background: var(--em-raised);
}
.card.is-off {
  opacity: 0.6;
}
.card h4 {
  margin: 0;
  font-size: 15px;
}
.portrait {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
}
.portrait img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  mix-blend-mode: lighten;
}
.letter {
  font-size: 52px;
  font-weight: 600;
  color: var(--em-accent);
}
.band {
  height: 36px;
  margin: calc(var(--em-space-4) * -1) calc(var(--em-space-4) * -1) 0;
  background: linear-gradient(color-mix(in srgb, var(--tier) 35%, transparent), transparent);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  font-size: 13px;
}
.owned {
  margin: 0;
  font-size: 12px;
  color: var(--em-muted);
}
.stock {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--tier);
}
.price {
  margin: 0;
}
.price strong {
  font-size: 18px;
}
.ribbon {
  position: absolute;
  top: 10px;
  right: -1px;
  padding: 2px 10px;
  background: var(--em-danger-surface);
  border: 1px solid var(--em-danger);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--em-danger);
}
.card input {
  min-height: var(--em-target);
  padding: 8px;
  border: 1px solid var(--em-border);
  border-radius: var(--em-radius);
  color: var(--em-text);
  background: var(--em-bg);
  font: inherit;
  text-align: center;
}
.hint {
  margin: var(--em-space-3) 0 0;
  font-size: 12px;
  color: var(--em-muted);
}
.block {
  width: 100%;
  margin-top: auto;
}
.empty {
  padding: 14px;
  border: 1px dashed var(--em-border);
  font-size: 13px;
  color: var(--em-muted);
}
@media (max-width: 700px) {
  .wallet {
    grid-template-columns: repeat(3, 1fr);
    gap: 20px 10px;
  }
  .balance {
    grid-column: 1 / -1;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--em-divider);
    text-align: center;
  }
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 420px) {
  .cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
```

- [ ] **Step 4: Run web checks**

Run (from `apps/ascension/web`): `npx vitest run` then `npx vue-tsc --noEmit`.
Expected: all PASS, including `radiusScale.test.ts` (no literal radii were added). Fix the existing e2e fake (`apps/ascension/web/e2e`) if it stubs the shop: add a `GET /ascension/shop` stub returning the same shape as `shopWindow()` and change its copies purchase to the `{ rotation, slot }` body.

- [ ] **Step 5: Commit boundary 2 (only when the user says "commit")**

```bash
git add apps/ascension/web
git commit -m "feat: Ascension shop shows rotating offers as cards"
```

---

## Phase C: Collection hover and notes (commit 3)

### Task 8: Collection card hover

**Files:**
- Modify: `apps/ascension/web/src/components/AscendedCard.vue`
- Modify: `apps/ascension/web/src/components/CollectionPanel.vue`
- Test: `apps/ascension/web/src/components/CollectionPanel.test.ts`

**Interfaces:**
- Consumes: `.em-lift` (Task 7).

- [ ] **Step 1: Write the failing test**

In `CollectionPanel.test.ts` add (using the file's existing mount helper and a profile with one owned Ascended and at least one missing one):

```ts
  it("lets owned and missing cards lift on hover", () => {
    const wrapper = mountPanel();

    expect(wrapper.find(".ascended-card").classes()).toContain("em-lift");
    expect(wrapper.find(".missing li").classes()).toContain("em-lift");
  });
```

Use the helper name that file already has for mounting with an owned list (do not invent a new one; copy the setup of the nearest existing test that renders owned and missing cards). Run it. Expected: FAIL.

- [ ] **Step 2: Implement**

In `AscendedCard.vue`: add `em-lift` to the root element's class list, add `:style="{ '--tier': ... }"` using the card's tier (`var(--em-tier-${ascended.tier_id}, var(--em-tier-common))`), add `is-off` while `down` (fainted) so a fainted card does not lift, and in the scoped style delete the `filter` transition and the `.ascended-card:hover { filter: brightness(1.1); }` rule (keep the focus-visible outline). In `CollectionPanel.vue` add `em-lift` to the missing-card `li` elements and give them `:style="{ '--tier': 'var(--em-border)' }"` so they glow neutral.

- [ ] **Step 3: Run**

Run: `npx vitest run` and `npx vue-tsc --noEmit` from `apps/ascension/web`.
Expected: PASS.

### Task 9: Docs and notes

**Files:**
- Modify: `apps/ascension/web/README.md`, `apps/ascension/README.md` (if not done in Task 5)
- Modify: `D:\User\Documents\Programming\Brain\Projects\` Ascension note, if one exists (use the file name that is there; follow `Brain/AGENTS.md`)

- [ ] **Step 1:** In `web/README.md` add a "Shop" section: offers load from `GET /ascension/shop`, the countdown runs from `seconds_left` on the device clock, a refresh or sold-out answer reloads the window, and `.em-lift` is the shared hover class.
- [ ] **Step 2:** Update the vault note for Ascension (rotating shop, schema version 3). Commit it in the Brain repo only when the user says "commit".
- [ ] **Step 3: Commit boundary 3 (only when the user says "commit")**

```bash
git add apps/ascension/web apps/ascension/README.md
git commit -m "feat: collection cards lift on hover, shop notes"
```

---

## Self-review

- **Spec coverage:** offers derivation (Task 1), stock by tier and weights (Task 1), storage and upgrade (Task 2), list and buy, errors, idempotency, fighting rule (Task 3), config and endpoints (Task 4), docs (Tasks 5 and 9), client, store, countdown (Task 6), cards, sold-out, countdown reload, EMBLEM and sell cards (Task 7), collection hover and `.em-lift` (Tasks 7 and 8), reduced motion (Task 7 CSS). The spec's "narrow screens" is the two media queries in Task 7. Stock-restore on a new rotation and old-row pruning are tested in Task 3.
- **Placeholders:** none; steps that depend on existing helper names (Task 8 test, Task 4 config tests) say to copy the neighbouring test's setup.
- **Type consistency:** `list_offers` keys match `ShopWindow`/`ShopOffer`; `buy_offer` result keys match `CopyPurchase`; `ShopService(repository, writer, catalog, progression, offers, clock)` is used the same in `composition.py`, `env.py` and `_price`.
