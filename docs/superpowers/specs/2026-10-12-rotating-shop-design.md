# Rotating shop: limited copy offers that change every 6 hours

Today the Ascension shop sells every regular Ascended's copy package at any time, without limit. This
design makes the copy side of the shop rotate: each account sees a small set of offers, each with a
limited stock, and the set changes every 6 hours. EMBLEMs and selling copies back stay as they are. The
shop page is redesigned with cards, and the collection cards get a subtle hover animation.

## Scope

1. Ascension backend (`apps/ascension`): derived per-account offers, a stock counter, a shop endpoint,
   a purchase by offer, and a database upgrade.
2. Ascension web (`apps/ascension/web`): shop client, store state, a card-based shop page with a refresh
   countdown, and a shared hover lift also used by the collection cards.

Out of scope: rotating EMBLEMs, a stock shared between players, discounts or price changes, buying
Forbidden Ascended, changes to selling copies back, changes to ember_api, ember_web or ember_admin.

## Decisions

| Question | Choice |
|---|---|
| Whose stock | Per account. Nobody competes for stock. |
| What rotates | Regular Ascended copy packages only. EMBLEMs stay always on sale and unlimited. |
| Rotation period | 6 hours: 00:00, 06:00, 12:00, 18:00 UTC |
| How offers exist | Derived from `(owner, rotation)` by a seeded pick. Only purchase counts are stored. |

## Offers

- `rotation = floor(now / shop_rotation_seconds)`. `now` comes from the existing injectable `Clock`.
- Per account and rotation, `shop_offers` (default 5) offers are chosen with a random source seeded from
  `(owner, rotation)`. The same account sees the same offers until the next rotation.
- An offer is one regular Ascended with one regular tier package (that tier's `copy_reward` copies) and a
  `stock`. Forbidden Ascended are never offered. Offers in one rotation are for distinct Ascended.
- Tiers are chosen with weights that make higher tiers rarer. Stock depends on the tier: Common 3,
  Rare 3, Unique 2, Royal 1, Legendary 1 (data in the catalog, `shop` section, keyed by the five regular tier ids).
- Price is unchanged: `ShopService.copy_price` works it out from the account's copies and level when it lists
  and when it buys. A purchase can still be refused with the existing Insufficient-Insignia 409 that states the cost.
- The rule that an Ascended fighting in the active battle cannot receive copies stays.

## Backend

- New class `ShopOffers` (pure, no I/O) in `src/ascension/shop_offers.py`: `window(owner, now) -> ShopWindow`
  with `rotation`, `refreshes_at` and the offers (`slot`, `ascended_id`, `tier_id`, `stock`).
  Deterministic for a given `(owner, rotation)` and the catalog.
- Table `shop_purchases (owner TEXT, rotation INTEGER, slot INTEGER, bought INTEGER, PRIMARY KEY (owner, rotation, slot))`.
  A purchase increments `bought` inside the same transaction that takes the Insignia and grants the copies,
  and deletes rows of older rotations for that owner.
- Database version 2 becomes 3. `SqliteAscendedRepository` today raises when the version differs. It gains
  an upgrade step: a version 2 database gets the new table and `user_version = 3`. Other versions still raise.
- `GET /ascension/shop` returns:
  `{ rotation, refreshes_at, seconds_left, offers: [{ slot, ascended_id, tier_id, copies_granted, stock, left, price, resulting_tier_id, owned_copies }] }`.
  `refreshes_at` is server time in seconds and `seconds_left` is what remains when the response is made. The page counts down
  from `seconds_left` on the device's own clock (the way the EMBLEM prompt does), never from `refreshes_at`.
- `POST /ascension/shop/purchases` with `{ kind: "copies", rotation, slot }` replaces the earlier
  `{ kind: "copies", ascended_id, tier }`. EMBLEM purchases are unchanged. The result is the existing copies
  result plus `left`. Errors:
  - 409 "the shop has refreshed" for a stale `rotation`;
  - 409 "sold out" when `bought >= stock`;
  - 400 for an unknown slot or a malformed body;
  - the existing 409 for insufficient Insignia and for a fighting Ascended.
  Purchases stay idempotent through the existing `Idempotency-Key` writer.
- Config (`configs/config_app.json`, documented in the README): `shop_rotation_seconds` (default 21600),
  `shop_offers` (default 5, 1 to 12).

## Web

- `AscensionClient.shop()` and `buyOffer(rotation, slot)`; `buyCopies(ascended, tier)` is removed.
- Store: `shop` state, `loadShop()`, `buyOffer(offer)`. The shop loads when the tab opens, after any purchase
  and after any 409 from it, and when the countdown reaches zero. A purchase updates `left` from the result.
- Shop page (`ShopPanel.vue`):
  - wallet strip unchanged;
  - "Offers" cards: portrait, name, tier badge, "+N copies", price, a "2 left" chip, Buy. Sold-out cards are
    dimmed with a "Sold out" mark. A header says "Refreshes in 3 h 12 m";
  - "Buy EMBLEMs": a grid of tier cards with the quantity input and Buy, dimmed when unaffordable;
  - "Sell a copy": one card per Ascended with absorbed copies;
  - the free-form "Buy Ascended copies" selects are removed.
- Hover: a shared `.em-lift` class in `theme.css` (rise 4px, scale 1.02, soft shadow, brighter border, 160 ms,
  tier-colored glow when a tier color exists, off under `prefers-reduced-motion`). Used by the shop cards
  and by `AscendedCard.vue` and the missing-Ascended template cards in the collection. Cards that are
  disabled or sold out do not lift.
- Layout: the grids drop to two columns and then one on narrow screens.

## Testing

- Pytest: offers are deterministic per `(owner, rotation)`, differ between rotations and accounts, are
  distinct Ascended, never Forbidden, and have the stock for their tier; stock limit and sold-out;
  stale rotation; unknown slot; idempotent replay; old rotation rows deleted; migration 2 to 3 keeps data;
  other versions still raise.
- Vitest: the cards, sold-out state, countdown and reload, error display, the EMBLEM and sell cards.
- Manual check by the user.

## Rollout, three commits

1. Backend: offers, table, upgrade, endpoint, purchase change, config, tests.
2. Web: client, store, shop page, tests.
3. Collection hover, `.em-lift`, README and vault notes.

Between commits 1 and 2 the old shop page cannot buy copies (the purchase body changes), so do them back to back.

## Risks

- Existing saves: the upgrade only adds a table. Other tables and owners' data are untouched.
- Server and device clocks can differ. The countdown uses the device clock from the moment the response
  arrives, the same as the EMBLEM prompt, and the server decides what the current rotation is.
- A player who has most Ascended already sees offers for them. That is intended: buying copies raises tiers.
