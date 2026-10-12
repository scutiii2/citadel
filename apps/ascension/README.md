# Ascension

Game backend for Ember: **Ascension**, a game of collecting and
battling **Ascended**, with a local Laya model helping the AI read the battle. It
never calls an LLM, so it costs nothing to play. Chess and Tetris will plug in
later as further games (see `docs/superpowers/` at the repo root).

Specs and plans: `docs/superpowers/specs/2026-10-10-emberlings-backend-design.md`
and `docs/superpowers/plans/2026-10-10-emberlings-backend.md`; the decision record
is `docs/superpowers/specs/2026-10-09-emberlings-decisions.md`.

Ascension serves its game API and its own built web UI. Ember registers the
game, hosts it in an iframe and supplies a one-time identity ticket. The
backend and standalone Vue UI are Phases 2 and 3 of
`docs/superpowers/plans/2026-10-11-game-host.md`. The generic Ember host follows
in Phase 4.

## The game in short

- You choose a starter Ascended (Guardian, Striker or Scout), then roll wild
  encounters. The preview shows the Ascended, tier and level; personalities stay hidden.
- A battle is 1v1 against a wild Ascended. Each round both sides choose in secret,
  then the actions are revealed and resolved together: SUPPORT, then DEFENSE,
  then a speed-weighted order for ATTACK, CATCH and FLEE.
- **CATCH** collects the wild Ascended with an EMBLEM. Winning or collecting pays XP
  and Insignia plus essence of the enemy's tier; collecting also adds copies and one random personality.
- Each Ascended starts at its own tier (`start_tier`). Spare copies and essence turn into stars, and enough
  stars raise the tier (see Stars and tiers). Insignia buys EMBLEMs and copies in the shop. EMBLEMs are always
  on sale. Copies come as a few limited offers per account that rotate every 6 hours (see Rotating shop).
- Play manually, or let your Ascended play on its own with a personality preset.

## How an Ascended chooses on its own

The engine owns the choice. Laya or the heuristic still reads three public-state values: danger, enemy
aggression and advantage. An uncertain, invalid, late or missing Laya value falls back to the heuristic.

The policy chooses in two stages:

1. A category from situation values, personality weights and the rules that fire. Only categories with a legal action
   share probability, so equipping three ATTACK abilities does not give ATTACK more category shares.
2. An action inside that category, using a softmax over a small potency term, repeat avoidance and any
   `pick_by_percentage` rule. The final seeded draw still picks from the combined action probabilities.

The same mood-lead draw chooses which personality instance leads each round. Match reading adds HP fractions,
HP lead and trend, round number, own category streak, the enemy's last category, damage taken last round and whether
the enemy has low HP. Three hidden mood meters are replayed from public battle history: **rage** rises with damage
and decays, **confidence** follows changes in the HP lead, and **nerves** follow losing and low HP.
They are recomputed on every decision; no new state is saved and restarting reproduces the same choice.
With personalities the decider uses one draw for the mood lead and one for the final action; without them, only the final draw.

Rules are data on each personality in `configs/ascension_catalog.json`: `when` holds conditions and the other keys
hold effects. Conditions include `lead_over`, `lead_under`, `own_hp_under`, `enemy_low`, `rage_over`,
`confidence_over`, `nerves_over`, `hit_taken_over`, `streak_over`, `round_under`, `round_over` and `enemy_last_is`.
An empty condition always holds. The eight effects are `multiply` (category factors), `chaos` (mass toward unlikely
categories), `counter`, `copy_enemy`, `break_streak`, `stay` (boost the last category), `repeat` and
`pick_by_percentage` (`high` or `low`). Rule strength is tier / 3, reduced by `off_mood_factor` for non-leading instances.
There are no ability style tags. The private audit records match, meters, category and action probabilities, and fired rules.
All rule values and mood constants are first guesses (?).

The first eight personalities retain their original category preferences; fourteen more act through rules:

| Personality | Behaviour |
|---|---|
| AGGRESSIVE | Prefers ATTACK. |
| DEFENSIVE | Prefers DEFENSE. |
| SUPPORTIVE | Prefers SUPPORT. |
| COWARD | Prefers FEAR (fleeing). |
| TENACIOUS | Prefers INTERCEPT (catching). |
| BOLD | Prefers ATTACK and SUPPORT. |
| CAUTIOUS | Prefers DEFENSE and FEAR. |
| DISCIPLINED | Prefers DEFENSE and SUPPORT. |
| WEIRD | Breaks a hidden category streak by jumping to its least likely other category (a turn to DEFENSE, SUPPORT or ATTACK, never a flee unless nothing else is left). |
| ANXIOUS | Adds chaos when nerves are high; stays plain while calm. |
| RECKLESS | Low HP raises ATTACK and lowers DEFENSE and FEAR. |
| VENGEFUL | Rage raises ATTACK. |
| BERSERKER | Rage raises ATTACK and suppresses FEAR; very low HP raises ATTACK again. |
| COCKY | High confidence raises ATTACK and lowers DEFENSE; losing adds chaos. |
| COMEBACK | Losing raises ATTACK and SUPPORT. |
| CUNNING | Counters enemy ATTACK with DEFENSE, and enemy SUPPORT or DEFENSE with ATTACK. |
| MIMIC | Boosts the enemy's last category. |
| PATIENT | Favours SUPPORT and DEFENSE early, ATTACK later or against low enemy HP. |
| OPPORTUNIST | Low enemy HP raises ATTACK and INTERCEPT; a healthy enemy raises DEFENSE. |
| STUBBORN | Removes repeat avoidance and boosts its previous category. |
| GAMBLER | Prefers high percentages while losing and low percentages with a strong lead. |
| STOIC | Has no rules or category preferences; the control group. |

`situation_source` in `configs/config_app.json` is `heuristic` (the default) or
`laya`. Choose `laya` only if `docs/ascension-laya-eval.md`, produced by the manual
evaluation, says so. EMBLEM choice after a timed-out prompt always asks Laya, and
falls back to basic ATTACK.

## Requirements

- Python 3.11 or newer on Windows (`py` launcher).
- Node.js and npm to build the Vue UI.
- Optional: the `laya` package (`pip install -e ".[laya]"`).

## Run

```
run.bat
```

The first start creates `.venv_ascension`, installs the project and creates
`configs/config_app.json` and `.env` from their `.example` twins. Both
real files are gitignored; `configs/ascension_catalog.json` (Ascended rules, abilities,
tiers, economy and policy numbers) is tracked. Put the same `INTERNAL_API_TOKEN`
in Ascension's local environment that `ember_api` uses. This token is used only
for outgoing server-to-server ticket redemption. Game routes always require a
bearer session, including when the internal token is missing. Game data lives
in `.data/ascension.sqlite3` (gitignored).
The database was renamed with the game (it was `data/sparks.sqlite3`, schema version 1; now `.data/ascension.sqlite3`, schema version 5).
Version 2, 3 and 4 files are upgraded to 5 on start (shop purchases, stars/essence and ability trees as needed). Version 1 fails with
`database schema version 1 is not supported`.
Delete the old file, or point `database_path` at a new one, to start fresh.

`server_launcher` lists this project from its `run.bat`. Default port 8060.
When `web/dist/index.html` is missing and `web/package.json` exists, the launcher
runs `npm --prefix web ci` followed by `npm --prefix web run build`. A build
failure stops the launcher. If UI sources are absent, the API still starts;
`/` returns 503 with
`UI not built: run npm --prefix web run build`.

## Ascended files

Everything that belongs to one Ascended lives in `ascended/<id>/` (rule in `AGENTS.md`, checked by
`tests/ascension/test_ascended_layout.py`): its `catalog.json` and up to three sprites,
`sprite_main_card.webp` (full card art), `sprite_preview_card.webp` (small card in the collection, shop and starter
list) and `sprite_battle.webp` (the battle arena). The game finds the sprites by file name when it loads the catalog,
lists them in each Ascended's `art` block of `/ascension/catalog` (a URL, or `null` when missing) and serves them at
`/ascended/<id>/<file>` with `Cache-Control: no-cache`, so replaced art shows after a reload. `catalog.json` may hold
`"art": {"focus": 21, "focus_preview": 50}`, the vertical crop centres (0 to 100, default 50) for the main and preview
sprites. Adding an Ascended is dropping a folder; a missing sprite falls back to another one, then to a letter.

An Ascended may also hold an animation sheet, `spreadsheet_animation.webp`, and `animations.json` beside it: the grid
(`columns`, `rows`) and, per state (`idle`, `attack`, `defend`, `support`, `flee`, `catch`), its `row`, `frames`,
`frame_ms` and `loop`. The catalog checks the file and lists it as `art.animation` (the sheet URL plus the grid), and the
sheet is served like a sprite. In battle the arena plays it instead of `sprite_battle.webp`: idle at rest, attack when
the fighter strikes, defend, support, flee, and catch while an EMBLEM is thrown at the other side. Ascended without a
sheet keep their still battle sprite.

## Stars and tiers

Power is the stat that drives damage, defence and fleeing. Essence is upgrade material, one kind per tier (grey,
green, blue, purple, gold, red), as in the Unity project.

- An Ascended is first owned at its `start_tier` (`ascended/<id>/catalog.json`, default `common`; Forbidden is always
  `forbidden`) and can rise no higher than its `end_tier` (default `legendary`). Shipped ladders: starters Common to
  Unique, Bruiser, Channeler and Sentinel Rare to Royal, Twoychi Unique to Legendary. A wild Ascended or shop offer only
  appears at a tier on its ladder. Tier only changes by a tier-up. It sets the stat multiplier.
- The first copy is the Ascended itself. Any further copy, from a capture or the shop, is a **spare copy** (`copies`).
- **A star** costs one spare copy and the tier's `essence_cost` in that tier's essence. Each tier has
  `stars_to_advance` (the Unity star ladder): Common 1, Rare 2, Unique 3, Royal 5. Legendary and Forbidden have none,
  and neither has the last tier of an Ascended's own ladder: it takes no stars and cannot rise.
- With enough stars an Ascended can **raise its tier** (free). The stars then start again from zero.
- Beating or collecting an enemy pays that enemy's tier `essence_cost` in its tier essence (Common 1, Rare 2, Unique 3,
  Royal 4, Legendary 5, Forbidden 10). Essence is never lost when a battle is lost.
- Selling a spare copy pays the Ascended's current tier and level and never changes the tier.
- Saved databases at version 3 keep each Ascended's tier (the one its absorbed copies had reached); those copies are spent.

## Ability trees

Each Ascended has an ability tree in `ascended/<id>/tree.json`, beside `catalog.json`. The Collection details
open an Ability tree view: select a node to learn it or equip it in a slot. The graph scrolls at phone width.
Tree balance numbers are placeholders (?).

The file is an object with a `nodes` list. Every node has a unique `id` and numeric `x`/`y` coordinates:

- Roots list `id`, `root: true`, `x` and `y`; for example, `{"id": "guardian_bulwark", "root": true, "x": 60, "y": 300}`.
  List every catalog ability and the passive root `<id>_passive`, plus `<id>_passive_2` when present.
  Their names and numbers come from `catalog.json`. The ability roots unlock at 1, 10, 20 (and 30 for the fourth).
  Roots are free and always learned. Without a tree file, the catalog supplies these four roots.
- Ability nodes have `kind: "ability"`, `name`, `category`, `percentage`, `cooldown`, `unlock_level` and optional `effects`.
  SUPPORT also has `stat` (`power` or `speed`) and `duration`.
- Passive nodes have `kind: "passive"`, `name`, `unlock_level` and `passive: {"kind": ..., "params": {...}}`,
  using an existing passive kind.
- Every non-root node has `requires` (prerequisite node ids) and `cost: {"tier": ..., "amount": ...}`.
  Costs spend a regular tier's essence. All prerequisites must lead back to roots; cycles and shared node positions are rejected.

Learning is permanent per account and needs the node's level, every prerequisite learned, and enough essence of
its cost tier. A successful learn spends that essence once; mutations accept an idempotency key for retries.
The seven basic Ascended (bruiser, channeler, cindrax, guardian, scout, sentinel, striker) keep three active
slots (`a1` to `a3`) and one passive slot (`p1`); any learned node of the matching kind fits.
Twoychi declares four active slots and two passive slots:

| Slot | Branches |
|---|---|
| A1 | Wolf abilities |
| A2 | Bear abilities |
| A3 | Dog abilities |
| A4 | Aya abilities |
| P1 | Wolf, Bear and Dog passives |
| P2 | Aya passives |

`tree.json` may declare `slots`, a mapping from slot ids to non-empty lists of lowercase branch names.
The declared slots are the Ascended's slots, including `a1` and `p1`, with active ids consecutive from `a1`.
Every node, including roots and cross-tree nodes, then needs one home `branch` and a slot of its kind that accepts it.
Without `slots`, branches impose no restriction and the basic 3+1 slots apply.
Only a tree declaring `a4` may have a fourth catalog ability; `p2` and catalog `passive_2` go together.
Twoychi's Waterbound (`heal_bonus`) is her second passive; Water is identity only, with no mechanic or form bonus.

`PUT /ascension/ascendeds/{id}/loadout` replaces the loadout with a slot map, for example
`{"slots": {"a1": "twoychi_troys_hunt", "a4": "twoychi_tidecall", "p2": "twoychi_passive_2"}}`.
Omitted or null slots are empty. At least one active slot must be filled; nodes must be learned, distinct,
and of the kind and branch that their slot accepts. The old `abilities`/`passive` request body is rejected.
The tree response lists the Ascended's slots with kind and branches, nodes with `branch`, and every slot in `loadout`.
The tree tab displays those slots and offers only the matching equip buttons.

When no loadout is saved, the catalog kit is equipped. Saved abilities resolve in slot order;
stale, unlearned or off-branch entries are ignored at battle start, with the default kit used if no active node survives.
Ability level gates still apply in battle. Two equipped passives act together: bonuses add, multipliers multiply,
defense limits take the best of each limit, start buffs concatenate, and cooldown reductions chain.

A battle freezes the equipped loadout when it starts. That Ascended's loadout cannot change during its active battle;
other Ascended can still change theirs. Database version 5 adds `learned_nodes` and `loadouts` without changing
version 4 data. Roots are implied rather than stored, and resetting progress removes both tables' rows for the player.

## Effects

Catalog abilities and ability nodes may carry an optional `effects` list, with at most three objects.
Each object has a `kind` and the fields below. Missing effects preserve the existing ability behavior;
saved battles without effects or statuses still load.

| Kind | Fields | Target and behavior |
|---|---|---|
| `heal` | `percentage` | Self: restores that percentage of power as HP, capped at max HP. |
| `regen` | `percentage`, `rounds` | Self: restores that amount each round. |
| `bleed` | `percentage`, `rounds` | Foe: deals that amount each round (at least 1), ignoring defense. |
| `slow` | `percentage`, `rounds` | Foe: lowers current speed by that percentage, with a stat floor of 1. |
| `weaken` | `percentage`, `rounds` | Foe: lowers current power by that percentage, with a stat floor of 1. |
| `exposed` | `percentage`, `rounds` | Foe: subtracts that amount of power from its shield rating, never below 0. |
| `mark` | `name`, `rounds`, optional `target` | A named mark; target is `foe` (default) or `self`. |
| `cleanse` | none | Self: removes bleed, slow, weaken and exposed; marks, regen and ward stay. |
| `ward` | `rounds` | Self: one lethal attack or bleed tick leaves 1 HP and consumes the ward. |

Percentages must be positive, durations at least one round, and mark names lowercase letters and underscores.
Unknown fields are rejected. Numbers are placeholders (?). Except slow and weaken, amounts use the caster's power:
unbuffed power for SUPPORT, current power for DEFENSE and ATTACK.

SUPPORT applies its buff then effects; DEFENSE applies its shield then effects. ATTACK applies effects after its hit
only while the target survives. At the end of a surviving round, the wild side ticks first, then the player;
each regenerates before bleeding. If both die from ticks, the player wins. A lethal bleed ends the battle without
advancing the round. Status rounds count down afterward, including the activation round, and zero-round statuses expire.

Fighters save statuses as `id`, `amount`, `rounds_left`. Applying the same id replaces its amount and duration;
statuses never stack. Marks use `mark:<name>` and have no effect until a passive reads them. A ward also expires
after its rounds. Public battle views show statuses and ability effects; revealed events describe heals, statuses,
cleanses, ticks and ward rescues. Bleed ticks do not count as attack damage in the hidden mood meters.

Two passive kinds read these mechanics: `attack_bonus_vs_marked` (`mark`, `power_fraction`) adds that fraction
of power as raw attack damage against the matching mark; `heal_bonus` (`fraction`, optional `hp_below`) multiplies
heals and regeneration by `1 + fraction`, optionally only below that share of max HP.
The autonomous policy does not yet account for wasting a heal at full HP.

For example, an attack node deals its normal damage, applies bleed and a prey mark if the foe survives, then
bleed ticks at the end of that round. All values below are placeholders (?).

```json
{"id": "twoychi_rending_bite", "name": "Rending Bite", "unlock_level": 10, "category": "ATTACK", "percentage": 180, "cooldown": 2,
 "effects": [{"kind": "bleed", "percentage": 20, "rounds": 3}, {"kind": "mark", "name": "prey", "rounds": 3}]}
```

## Rotating shop

Every `shop_rotation_seconds` (default 21600, so 00:00, 06:00, 12:00 and 18:00 UTC) each account gets
`shop_offers` (default 5, 1 to 12) copy offers. An offer is one regular Ascended with one tier package and a limited
stock (Common 3, Rare 3, Unique 2, Royal 1, Legendary 1; set under `shop` in `configs/ascension_catalog.json`).
Offers are derived from the account and the rotation, so they are the same until the next rotation and no stock is
shared between players. Only purchase counts are stored (`shop_purchases`). Prices are worked out when you list or
buy, from the copies and level you have. A purchase with an old `rotation` is refused with a 409 ("the shop has
refreshed"); a used-up offer is a 409 "sold out".

## Ember host configuration

Add these required fields to an existing `configs/config_app.json`, using the
values in `configs/config_app.json.example`:

| Setting | Example/default | Purpose |
|---|---|---|
| `ember_api_url` | `http://127.0.0.1:8030` | Ember API base URL; 8030 is its actual default port |
| `ember_origin` | `http://127.0.0.1:5173` | Single Ember web origin allowed to frame the game |
| `session_hours` | `8` | Absolute session lifetime; reads do not extend it |
| `game_id` | `ascension` | Game id sent to Ember when redeeming a ticket |
| `dev_fake_owner` | empty string | Optional fixed local owner; empty disables it |
| `shop_rotation_seconds` | `21600` | How long one shop rotation lasts (at least 60) |
| `shop_offers` | `5` | Copy offers per account and rotation (1 to 12) |

`ember_origin` must be an http/https origin without credentials, a path, query
or fragment. Keep it equal to the UI's `VITE_EMBER_ORIGIN` setting when Phase 3
adds `HostBridge`; that value controls the browser's `postMessage` target.

## Ticket redemption and UI serving

`POST /session/redeem` accepts only `{ "ticket": "..." }`. Ascension sends the
ticket and configured `game_id` to Ember's `/internal/games/tickets/redeem`
with its internal header. Ember returns the account id as text; that remains
the owner of saved data. A successful request returns a random 256-bit token
and `expires_in` seconds. The browser keeps the token in memory and sends
`Authorization: Bearer <token>` on game calls. No cookies are involved.
Sessions expire without refresh, are capped at 1,000 (oldest evicted), and
are lost on process restart.

Redemption is limited to 10 attempts per 60 seconds per socket peer IP;
invalid tickets and malformed bodies count too. Responses are 400 for a bad
body, 401 `{"error": "Invalid ticket"}` for a rejected ticket, 502
`{"error": "Ember is not available"}` for an unavailable or malformed Ember
response, and 429 after the limit. Ember's internal token is never sent to the
browser, and redirects are never followed by the identity client.

For local development only, setting `dev_fake_owner` lets ticket `dev` open a
session for that owner without calling Ember. Other tickets still go through
Ember, and the same rate limit applies. Leave the setting empty for normal use.

`GET /manifest.json` is public. `web/dist` supplies `index.html` and `/assets/*`.
Non-file UI paths use the SPA fallback; missing assets, dotted file requests,
traversal, and the `/ascension`, `/session`, and `/health` namespaces never use
that fallback. Resolved asset and index paths must remain within the build.
UI and manifest responses set `Content-Security-Policy` with
`frame-ancestors <ember_origin>`, `X-Content-Type-Options: nosniff`, and
`Referrer-Policy: no-referrer`; they do not set `X-Frame-Options`.

Phase 2 changes the game's auth protocol. The legacy Ember proxy still sends
the old headers and cannot play this backend until the later host/UI phases
complete the ticket flow.

## API

Every `/ascension` route, including the catalog, needs a valid
`Authorization: Bearer <token>` session. `/health`, `/manifest.json`, the UI and
`/session/redeem` are public. Legacy requester and internal headers cannot
identify a player. Mutations also need an
`Idempotency-Key` header; a retry with the same key returns the first result.
Bodies reject unknown fields. Round mutations carry the `round` and `revision` you
last saw; a stale pair is a 409.

| Route | Purpose |
|---|---|
| `GET /ascension/catalog` | Ascended, abilities, tiers, personalities, shop data |
| `GET /ascended/{id}/{file}` | Public sprite files (`sprite_main_card`, `sprite_preview_card`, `sprite_battle`, `spreadsheet_animation`, `.webp`); any other path is a 404 |
| `POST /ascension/profile` | Create the profile with a starter |
| `POST /ascension/profile/reset` | Delete all of the player's progress (needs `confirm: true`) |
| `GET /ascension/profile` | Wallet, Ascended, timers, pending encounter, active battle |
| `GET /ascension/ascendeds/{id}/personalities` | Collected personality instances (paginated) |
| `GET`/`PUT /ascension/ascendeds/{id}/presets/{slot}` | One of five presets (up to three instances) |
| `POST /ascension/encounters` | Roll a preview (one per 30 seconds) |
| `GET /ascension/encounters/{id}` | The same preview, never rerolled |
| `POST /ascension/encounters/{id}/decline` | Decline for free |
| `POST /ascension/battles` | Start the battle: Ascended, preset, mode, EMBLEM limit |
| `GET /ascension/battles/{id}` | Public state, legal actions, history, result |
| `POST /ascension/battles/{id}/actions` | Manual action for a round |
| `POST /ascension/battles/{id}/emblem` | Answer the five-second EMBLEM prompt |
| `POST /ascension/battles/{id}/advance` | Play one autonomous round, or settle an expired prompt |
| `POST /ascension/battles/{id}/mode` | Switch manual or autonomous between rounds |
| `POST /ascension/battles/{id}/forfeit` | End as a loss |
| `GET /ascension/shop` | This account's current offers: `rotation`, `seconds_left`, and per offer `slot`, Ascended, tier, `stock`, `left`, `price` |
| `POST /ascension/shop/purchases` | Buy EMBLEMs (`{kind: "emblem", tier, quantity}`) or an offer (`{kind: "copies", rotation, slot}`) |
| `GET /ascension/ascendeds/{id}/tree` | Nodes with learned, learnable or locked state, essence and equipped slots |
| `POST /ascension/ascendeds/{id}/tree/{node}/learn` | Learn a node with level, prerequisites and essence |
| `PUT /ascension/ascendeds/{id}/loadout` | Replace equipped slots (`{slots: {a1: node id, p1: node id or null, ...}}`) |
| `POST /ascension/ascendeds/{id}/sales` | Sell one spare copy |
| `POST /ascension/ascendeds/{id}/stars` | Add a star (one spare copy and the tier's essence) |
| `POST /ascension/ascendeds/{id}/tier` | Raise the tier once the stars are full |

`POST /ascension/profile/reset` deletes the player's profile, Ascended, personalities, presets, EMBLEMs, encounters and battle history so a starter can be chosen again; it needs `{"confirm": true}` and is refused with a 409 while a battle is active.

Errors: 400 bad input or unknown Ascended or tier, 401 `Not signed in` for a
missing, invalid or expired bearer session, 404 missing or
someone else's record, 409 state conflict (stale revision, wrong phase, not enough
Insignia, essence or copies, stars not ready, cooldown, one active battle).

Closing the game view simply stops calls to `advance`: the battle stays saved
between rounds and resumes where it was, including an open EMBLEM prompt and its
deadline. Timers run in real time while the service is stopped.

## Tests and the Laya evaluation

```
.venv_ascension\Scripts\python -m pytest
.venv_ascension\Scripts\python -m src.ascension.eval.situation_eval
```

The tests use a fake Laya engine. The evaluation needs the real model, is run by
hand and writes `docs/ascension-laya-eval.md`.

## Catalog

The global rules (tiers, levels, economy, personalities, action policy) live in
`configs/ascension_catalog.json`. Each Ascended has its own folder in `ascended/`, named
after its id, holding its `catalog.json` (`ascended/guardian/catalog.json` has
`"id": "guardian"`); its assets will sit beside it. Folders load in alphabetical
order, which is the Ascended order and keeps random draws deterministic. Folders
without a `catalog.json` and loose files (the shared card placeholders
`ascended_common_front_template.png` and `ascended_common_back_template.png`) are
skipped. Both locations are fixed in the project tree and have no config entry.

Each Ascended file may list `"ascension_types"`, zero or more of `pure`, `abyss`,
`divine`, `crimson`, `enchant` and `synthetic` (the Ascension game's types). An
unknown or repeated type stops startup. For now a type only filters and groups
the collection; it has no effect in battle. Every Ascended has `enchant`; Twoychi is also `divine`.

## Layout

- `src/` - config, bearer auth, sessions, Ember identity client, UI serving,
  the Laya client and the FastAPI app.
- `manifest.json` - public game metadata.
- `web/` - standalone Vue game UI, tests, fonts and card art; `web/dist/` is the build.
- `src/ascension/` - Ascension: catalog, battle engine, passives, action policy and
  decider, situation readers, repository, services, coordinator, API.
- `src/ascension/eval/` - the manual Laya evaluation.
- `configs/`, `.env` - gitignored real files with `.example` twins, plus the
  tracked `ascension_catalog.json`. `.env` and `.env.example` sit in the project root,
  beside `configs/`.
- `.data/` - SQLite database (created at runtime, gitignored).

## Behaviour notes

- **EMBLEM fallback.** When an autonomous battle's EMBLEM prompt expires, the
  picker chooses among the tiers the player may spend. With exactly one permitted
  tier it uses that tier. With two or more and no Laya, the autonomous CATCH
  becomes a basic ATTACK.
- **Port.** The launcher's `ASCENSION_PORT` entry is only a launcher default.
  The real port is `port` in `configs/config_app.json`; keep the two equal.

## Known gaps

Remaining gameplay gaps:

- The mood draw is stored in `rounds`, but no route reveals it after a battle has
  finished.
- Manual gameplay verification remains a user check.

## Standalone web UI

See [web/README.md](web/README.md) for development and build commands. The UI now
lives in this project and calls `/ascension` directly with an in-memory bearer
session. Run `npm --prefix web ci`, then `npm --prefix web run build` after UI
changes. `run.bat` installs and builds automatically when `web/dist/index.html`
is missing, then FastAPI serves the build.

The Vite dev port defaults to 5174 and proxies game requests to port 8060. Set
`VITE_EMBER_ORIGIN` before development/build to match the backend's `ember_origin`
(default `http://127.0.0.1:5173`); a mismatch can block iframe loading or messages.
Without a launch ticket, the page says “Open this game from Ember”. An expired
session asks the player to reopen the game; it does not retry the spent ticket.

## Launch from Ember

Set `ember_api_url` to `http://127.0.0.1:8030` and `ember_origin` to the Ember
web origin (default `http://127.0.0.1:5173`). Configure the same internal token
on both servers yourself; it is only used by the server-side redeem client.
Register `http://127.0.0.1:8060` in Ember Admin's Games page and grant
`games.ascension.play` to player roles. Administrator receives the grant on
registration. Build with `VITE_EMBER_ORIGIN` matching `ember_origin`.
