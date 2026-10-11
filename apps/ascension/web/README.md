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

The migrated Playwright smoke test is self-contained and uses a fake game API.
`npm run test:e2e` launches a browser; agents do not run it. Manual verification
belongs to the user.

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
