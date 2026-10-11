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
backend changes are Phase 2 of `docs/superpowers/plans/2026-10-11-game-host.md`;
the Vue sources move into `web/` in Phase 3.

## The game in short

- You choose a starter Ascended (Guardian, Striker or Scout), then roll wild
  encounters. The preview shows the Ascended, tier and level; personalities stay hidden.
- A battle is 1v1 against a wild Ascended. Each round both sides choose in secret,
  then the actions are revealed and resolved together: SUPPORT, then DEFENSE,
  then a speed-weighted order for ATTACK, CATCH and FLEE.
- **CATCH** collects the wild Ascended with an EMBLEM. Winning or collecting pays XP
  and Insignia; collecting also adds copies and one random personality.
- Ascended keep absorbed copies, which set their tier; Insignia buys EMBLEMs and
  copies in the shop.
- Play manually, or let your Ascended play on its own with a personality preset.

## How an Ascended chooses on its own

A fixed personality fed to a classifier would pick the same action every time, so
the engine owns the choice. Laya only reads the situation:

1. Laya answers three short typed questions (danger, enemy aggression, advantage)
   about a public-state text. If a read is uncertain, invalid, late or missing, an
   engine heuristic supplies that value instead.
2. The engine turns those values, the round's personality weights (one equipped
   personality leads each round), a potency term and a repeat penalty into action
   probabilities, then draws with the battle's seeded random stream.

`situation_source` in `configs/config_app.json` is `heuristic` (the default) or
`laya`. Choose `laya` only if `docs/ascension-laya-eval.md`, produced by the manual
evaluation, says so. EMBLEM choice after a timed-out prompt always asks Laya, and
falls back to basic ATTACK.

## Requirements

- Python 3.11 or newer on Windows (`py` launcher).
- Node.js and npm to build the Vue UI once `web/package.json` is present.
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
The database was renamed with the game (it was `data/sparks.sqlite3`, schema version 1; now `.data/ascension.sqlite3`, schema version 2).
There is no migration: a start with an old file fails with `database schema version 1 is not supported`.
Delete the old file, or point `database_path` at a new one, to start fresh.

`server_launcher` lists this project from its `run.bat`. Default port 8060.
When `web/dist/index.html` is missing and `web/package.json` exists, the launcher
runs `npm --prefix web ci` followed by `npm --prefix web run build`. A build
failure stops the launcher. During Phase 2, when the UI sources are absent, it
starts the API anyway; `/` returns 503 with
`UI not built: run npm --prefix web run build`.

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
| `POST /ascension/shop/purchases` | Buy EMBLEMs or regular-Ascended copies |
| `POST /ascension/ascendeds/{id}/sales` | Sell one absorbed copy |

`POST /ascension/profile/reset` deletes the player's profile, Ascended, personalities, presets, EMBLEMs, encounters and battle history so a starter can be chosen again; it needs `{"confirm": true}` and is refused with a 409 while a battle is active.

Errors: 400 bad input or unknown Ascended or tier, 401 `Not signed in` for a
missing, invalid or expired bearer session, 404 missing or
someone else's record, 409 state conflict (stale revision, wrong phase, not enough
Insignia, cooldown, one active battle).

Closing the game view simply stops calls to `advance`: the battle stays saved
between rounds and resumes where it was, including an open EMBLEM prompt and its
deadline. Timers run in real time while the service is stopped.

## Tests and the Laya evaluation

```
.venv_mini_games\Scripts\python -m pytest
.venv_mini_games\Scripts\python -m src.ascension.eval.situation_eval
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
the collection; it has no effect in battle. All current Ascended are `enchant`.

## Layout

- `src/` - config, bearer auth, sessions, Ember identity client, UI serving,
  the Laya client and the FastAPI app.
- `manifest.json` - public game metadata.
- `web/dist/` - built game UI (Vue sources arrive in Phase 3).
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

Deferred to the Ember UI spec:

- The mood draw is stored in `rounds`, but no route reveals it after a battle has
  finished.
- The manifest supplies game discovery; the Vue UI sources arrive in Phase 3.
