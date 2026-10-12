# Ascension web

Standalone Vue 3 + TypeScript + Pinia UI, served by Ascension's FastAPI backend.
The game has no router and talks directly to `/ascension`, with bearer sessions.

## Development

From this directory:

```powershell
npm ci
npm run dev
```

Vite binds to `127.0.0.1:5174`. `ASCENSION_WEB_PORT` changes the dev port.
`/ascension`, `/session` and `/health` proxy to `http://127.0.0.1:8060`.
Run the game backend separately. The Ember API defaults to port 8030.

`VITE_EMBER_ORIGIN` is the exact host origin used by postMessage, defaulting to
`http://127.0.0.1:5173`. Set it before starting Vite or building if Ember uses
another origin. It must match the backend's `ember_origin` setting; a mismatch
can block the iframe or prevent host messages. Do not use a wildcard.

Open the game through Ember. Without a launch ticket it displays
“Open this game from Ember”. For local development only, a backend configured
with a nonempty `dev_fake_owner` accepts the fixed `dev` ticket at `/#ticket=dev`.
Keep that flag empty in production. The host UI arrives in Phase 4.

## Build and verify

```powershell
npx vue-tsc -b
npx vitest run
npx vite build
```

The build writes `dist/`, including fonts and card art. The parent `run.bat`
runs `npm ci` and builds when `dist/index.html` is missing. After source changes,
rebuild with `npm run build`. FastAPI serves the UI and security headers on the
game's port; Vite preview is only a local build preview.

The Playwright smoke tests are self-contained and use a fake game API.
`npm run test:e2e` launches a browser and checks the collection, starter and battle
preparation screens at desktop and mobile sizes.

## Squad and battle preparation

The Collection tab shows one slot per configured squad position. Use the detail
dialog to add or remove a member, or remove one directly from the strip. The last
member cannot be removed, and active battles lock equipment changes.

Battle preparation lists the squad in position order, with empty slots and fainting
countdowns. The first ready member is selected; click a card or press Enter or Space
to choose another. Fainted members cannot be selected. The selected member appears
as a full card beside the battle plan. The shared `EmPickCard` component owns the
starter and squad pickers' copper outline and breathing glow, including its reduced
motion rule. On small screens the squad wraps above the full card.

Battle results keep the fighter's XP reward prominent and list the other squad
members' shares and level-ups underneath it.

## HostBridge

The bridge reads the launch ticket from the URL fragment, clears the fragment
before redemption starts, then posts JSON to `/session/redeem`. Its session token
stays in memory and is added to every game request. Requests omit cookies and
reject redirects. A 401 clears the session, stops the battle loop and displays
“Session ended, reopen the game from Ember”. The spent ticket is never retried.

Outgoing messages are `{source: "game", type: "ready"}`, resize with a positive
`height`, and close, all sent to the configured Ember origin. The only incoming
command is `{source: "host", type: "close"}`; both the origin and parent window
must match. Resize observers and message listeners are removed when the UI
unmounts. Closing a game preserves its server-side progress.

The radius-scale test scans all Vue/CSS sources. Components use the copied
radius tokens or the existing Ascension theme tokens, without literal radii.

## Battle animation

`src/stores/playback.ts` plays each new round of a battle as short steps (`src/utils/battleCues.ts` maps
server events to them): attack lunge, hit shake with a floating damage number, defense glow, support glow,
EMBLEM throw with wobble, caught or broke free, flee. The arena shows the old health until a hit lands.
While it plays, the action buttons are locked and the result screen waits; the Skip button or a click on
the arena jumps to the end. Nothing plays when a battle is opened or restored, or while an EMBLEM prompt is
open (its countdown is running). It always plays, even with `prefers-reduced-motion`: `.em-glow` on the arena
exempts it from the global reduced-motion rule in `theme.css`.

## Shop

The Shop tab loads `GET /ascension/shop`: this account's copy offers for the current rotation (each with `left` of
`stock`) while EMBLEMs stay always on sale. `seconds_left` from the answer is counted down on this device's clock
(`store.shopEndsAt`), never from the server's timestamp. At zero, after a purchase and after any refusal the page
loads the window again, so a rotation, a sold-out offer or a stale `rotation` (409 "the shop has refreshed") never
leaves old cards on screen. Sold-out and unaffordable cards carry `is-off`. `.em-lift` in `theme.css` is the shared
hover glow (rise, crisp tier-coloured ring and a wide soft bloom) used by the shop, collection and starter cards; it is off under
`prefers-reduced-motion` and for `is-off` cards.

## Sprites

Sprites are not part of the web build. Each Ascended's folder in `../ascended/<id>/` holds
`sprite_main_card.webp`, `sprite_preview_card.webp` and `sprite_battle.webp`; the game serves them at
`/ascended/<id>/<file>` and lists the URLs in the catalog (`AscendedInfo.art`). `spriteFor(art, slot)` in
`src/utils/sprites.ts` picks one: the full card uses the main sprite, the small card (collection, shop offers,
starter list) the preview sprite, and the battle arena the battle sprite. A missing slot falls back to the first
sprite that exists, then to the letter placeholder.

An Ascended with an animation sheet (`AscendedInfo.art.animation`) is drawn in battle by `ui/AnimatedSprite.vue`
instead of the still sprite: the sheet is one background image and CSS `steps()` moves it across the frames, one row per
state. `poseFor(fx, catching)` in `src/utils/sprites.ts` picks the state from the playback effect (lunge is attack,
guard is defend, boost is support, flee is flee, an EMBLEM thrown at the other side is catch, anything else idle). The dev server proxies `/ascended` to the game.
