# ember

Ember Windows app: the `ember_web` UI (Vue 3, TypeScript, Vite) in a Tauri 2 shell. It replaces `ember_web`, which is disabled and kept only as reference.

## How it talks to the server

- The user enters the Portcullis address once on the login page (`src/utils/server.ts`, stored in `localStorage` as `ember.server_url`).
- Login sends `X-Ember-Client: desktop`; Portcullis then adds `session_token` to the login answer. The app sends it as `Authorization: Bearer ...` on every call (REST, the turn event stream, the MCP client). No cookie is used: the SameSite=Strict cookie does not cross origins.
- Portcullis allows the desktop origins (`tauri://localhost`, `http://tauri.localhost`, `https://tauri.localhost`) through CORS, without credentials. Set `desktop_origins` in its `config_app.json` to change the list.
- `<img>` and `<audio>` cannot send a header, so image attachments and Bard audio are fetched and shown as `blob:` URLs (`mediaUrl`).
- In a plain browser (`pnpm dev`, port 26506, `/api` proxied to Portcullis) it behaves like `ember_web` (cookie, same origin).

## Run and build

- `pnpm install`, then `pnpm dev` (browser) or `pnpm tauri dev` (window). Needs Rust (<https://rustup.rs>) for `tauri`.
- `pnpm tauri build` makes the NSIS installer (per-user) under `src-tauri/target/release/bundle/nsis`.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`.

## Not working yet in the Windows app

- Live dictation (a WebSocket, which cannot carry the bearer): it falls back to recording, then transcribing.
- Direct file links that are not images or Bard audio: the PDF merger and media downloader pages, and downloads linked from chat. They need the same `mediaUrl` treatment.
- Shared-chat links point at `<server>/shared/<token>`, but Portcullis serves no web page there since `ember_web` is off. The app's own `/shared/:token` page works inside the app only.
- No web push and no offline banner (the PWA code was removed). Native notifications are a later step.
- No calendar or games page: `ember_web` never had them.
