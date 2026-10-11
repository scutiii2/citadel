# Game host: Ascension gets its own UI server, Ember hosts games in an iframe

Today the Ascension game's backend (`apps/ascension`, port 8060) is reached through ember_api's
`/api/ascension` proxy, and its UI lives inside ember_web (`components/ascension`, `AscensionView`,
route `/ascension`). This design separates them. Ascension ships and serves its own web UI. Ember
becomes a host that registers games by URL and plays them in an iframe.

Source request (`_TODO.md`, "Split Ascension out of mini_games and make the Ember page a game host"):
the game has its own web UI server and does not share one with ember_web, and the ember_web games page
acts as an emulator that can register and deregister games by their URLs.

## Scope

1. Ascension serves its own web UI and exposes its own game API. ember_api no longer proxies game traffic.
2. ember_api keeps a registry of games, registered by URL, and vouches for the player's identity.
3. ember_web's `/ascension` page becomes a generic `/games` host with an iframe stage.
4. ember_admin manages the registry (register, refresh, deregister).

Out of scope: a second game, game-to-game features, payments or shared currency across games, Unity
Ascension, game-specific permissions beyond play, moving `apps/mini_games` (stays an empty folder).

## Decisions

| Question | Choice |
|---|---|
| How the host shows a game | iframe |
| Identity and data path | one-time launch ticket; the game owns its data path, ember_api only vouches for identity |
| Registry | admin-managed in the ember_api DB, driven by a manifest at the game's URL |
| UI location | Vue project inside the game (`apps/ascension/web/`), served by the game's own FastAPI |

## Pieces

- **Ascension** (`apps/ascension`): backend as now, plus `web/` (Vue 3 + TS, Vite, Vitest) built to
  `web/dist` and served by the same FastAPI at `/`. New routes: `GET /manifest.json`,
  `POST /session/redeem`. Game routes use a bearer session instead of the internal token.
- **ember_api**: `games` registry, launch tickets, internal redeem endpoint. The `/api/ascension` proxy,
  `AscensionGateway` and `ascension_url` config are deleted.
- **ember_web**: `/games` host view, `GameStage` iframe component, games store and client. All Ascension
  UI code leaves.
- **ember_admin**: game management page.

## Launch flow

1. The host lists games (`GET /api/games`), filtered to those the account may play (`games.<id>.play`).
2. The player picks one. The host calls `POST /api/games/{id}/launch` and gets the game URL with a one-time
   ticket in the URL fragment. A fragment is never sent to a server or written to a log.
3. The iframe loads the game UI. Its script posts the ticket to the game's `POST /session/redeem`.
4. The game backend redeems the ticket with ember_api (server to server, internal token). ember_api returns the
   account id and display name and burns the ticket (about 60 seconds, single use).
5. The game returns a random, expiring session token kept server-side. The UI keeps it in memory and sends
   `Authorization: Bearer`. No cookies, so third-party cookie blocking in iframes cannot break it. The data owner
   key stays the account id as text, so existing saves keep working.
6. Standalone: without a ticket the game UI shows "Open this game from Ember". A dev-only config flag may
   mint a fixed fake owner for local work.

## Registry (ember_api)

- Table `games`: `id` (slug from the manifest), `url` (normalised base), `name`, `description`, `icon`,
  `version`, `enabled`, `manifest` (JSON snapshot), `created_at`.
- Table `game_tickets`: `hash` (SHA-256 of the ticket, never the ticket), `game_id`, `account_id`, `expires_at`,
  `used_at`. Expired rows are pruned on launch.
- Manifest at `<url>/manifest.json`: `id`, `name`, `description`, `icon`, `version`. Validated on register and refresh.
- Permission per game: `games.<id>.play`, created on register. Deregister deletes the game row; the permission
  and its role grants stay, so a later re-register restores access.
- Migration 0014: creates both tables and renames permission `ascension.play` to `games.ascension.play`,
  keeping role grants. The downgrade reverses the rename.
- Routes:
  - `GET /api/games`
  - `POST /api/games/{id}/launch`, needs `games.<id>.play`
  - admin: `POST /api/games` (`{url}`), `POST /api/games/{id}/refresh`, `DELETE /api/games/{id}`
  - internal, internal-token only: `POST /internal/games/tickets/redeem` (`{ticket, game_id}` returns
    `{account_id, display_name}`). Unknown, expired, used and wrong-game tickets all return one generic 401.
- Audit log actions: `games.register`, `games.refresh`, `games.deregister`, `games.launch`.

### Registering a URL safely

Only http or https, no credentials in the URL. The manifest fetch has a timeout, a size cap and no redirects,
and the response must be JSON with a valid `id`. Private and loopback targets are allowed only when config
`games_allow_private_urls` is true (true in the example config for local dev, documented as off for production).

## Ascension backend

- `GameSession` store: in memory, expiring, random 256-bit tokens. Restart logs players out; they relaunch.
- Config: `ember_api_url`, `ember_origin` (drives `frame-ancestors` and the `postMessage` target origin),
  `dev_fake_owner` (off by default).
- Game routes switch from `X-Internal-Token` plus requester header to the bearer session. The internal token
  remains for the outgoing redeem call and `/health` is open.
- Serves `web/dist` with SPA fallback and security headers. The repository schema is unchanged, so no data migration.

## Ascension web (`apps/ascension/web/`)

Moved from ember_web: `components/ascension`, the view (becomes `App.vue`), `AscensionClient`, store, utils,
assets, e2e, theme and fonts. New class `HostBridge` handles ticket redeem, bearer injection and the
`ready`, `resize` and `close` messages. Own `package.json`, README, tests. `run.bat` builds the UI when
`dist` is missing.

## ember_web and ember_admin

- `GamesView` at `/games`; `/ascension` redirects. `GameStage` renders the iframe with
  `sandbox="allow-scripts allow-same-origin allow-forms"` (`allow-forms`: a sandbox without it
  silently blocks the game's form submits, such as Begin battle), listens only for `ready`, `resize`, `close` from the game's origin.
- CSP `frame-src` lists only registered game origins, built from the registry, never a wildcard.
- ember_admin page: list, register by URL, refresh, deregister (type-to-confirm, per the UI conventions).

## Testing

- Pytest: registry CRUD, manifest validation, SSRF cases, ticket replay, expiry and wrong game, session auth,
  proxy removal, migration up and down. The 588 Ascension tests adapt to bearer auth.
- Vitest: `GamesView`, `GameStage`, `HostBridge`, moved components. Playwright e2e moves with the game UI.
- Manual end-to-end check by the user.

## Rollout (four commits, each green)

1. ember_api: registry, tickets, migration 0014. The old proxy still works.
2. Ascension backend: manifest, redeem, bearer auth, static serving.
3. Ascension web: move the UI out of ember_web into `apps/ascension/web/`.
4. ember_web `/games` host and ember_admin page. Then delete the old proxy, `ascension_url`, update Server
   Launcher notes, README files, vault notes and the TODO.

Between commits 2 and 4 the ember_web Ascension page is broken (the proxy auth changes). Commits 2 to 4 are
therefore best done back to back before the user tests.

## Risks

- Cross-origin iframes need correct CSP on both sides. Mitigation: origin lists come from config and registry only.
- A registered game is trusted code in an iframe. The sandbox, origin-checked messages and admin-only
  registration limit the exposure; a malicious registered game could still phish inside its frame. Admin trust is assumed.
- Ticket in the URL fragment can leak through a screenshot or shared link. Short life and single use limit it.
- Large move of UI code. Another session has uncommitted ember_web work; only my files and hunks are staged.
- Existing game saves stay valid only if the owner key (account id text) is unchanged. It is.
