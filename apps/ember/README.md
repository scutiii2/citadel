# ember

Ember Windows app: the `ember_web` UI (Vue 3, TypeScript, Vite) in a Tauri 2 shell. It replaces `ember_web`, which is disabled and kept only as reference.

## How it talks to the server

- The Windows app opens on a **Connect to your server** screen (`ConnectView.vue`) until a Portcullis address has answered `GET /api/health`. Only then is it saved (`src/utils/server.ts`, `localStorage` key `ember.server_url`), and only then do login, register and every other page open. The router guard checks a saved address again on each launch; an unreachable server sends the user back to the connect screen with the reason, and the same happens mid-session when a call cannot reach the server. The login page shows the server with a **Change** link. Switching to a different server drops the old session.
- Login sends `X-Ember-Client: desktop`; Portcullis then adds `session_token` to the login answer. The app sends it as `Authorization: Bearer ...` on every call (REST, the turn event stream, the MCP client). No cookie is used: the SameSite=Strict cookie does not cross origins.
- Portcullis allows the desktop origins (`tauri://localhost`, `http://tauri.localhost`, `https://tauri.localhost`) through CORS, without credentials. Set `desktop_origins` in its `config_app.json` to change the list.
- `<img>` and `<audio>` cannot send a header, so image attachments and Bard audio are fetched and shown as `blob:` URLs (`mediaUrl`).
- In a plain browser (`pnpm dev`, port 26506, `/api` proxied to Portcullis) it behaves like `ember_web` (cookie, same origin).

- **Global** follows **Shares** in navigation. Signed-in accounts can browse and search global files and active skills. Accounts with `brain.global.write` can also manage files and skills and review shares sent to the global brain.

## Run and build

- `pnpm install`, then `pnpm dev` (browser) or `pnpm tauri dev` (window). Needs Rust (<https://rustup.rs>) for `tauri`.
- `pnpm tauri build` makes the NSIS installer (per-user) under `src-tauri/target/release/bundle/nsis`.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`.

## Windows app specifics

- Live dictation works over a WebSocket. It cannot carry a header, so the app offers its token as the subprotocol pair `ember.bearer, <token>`; Portcullis accepts that only from a configured desktop origin. If the socket fails, it falls back to recording, then transcribing.
- File links (chat download cards, PDF merger, media downloader) are fetched with the bearer and saved from a blob (`saveFile` in `src/utils/server.ts`).
- Shared-chat links (`<server>/shared/<token>`) open a read-only page that Portcullis serves itself (plain HTML, no script).
- Completion alerts use the web `Notification` API of the WebView2 window. No Tauri notification plugin is added.

## Not done

- The Tauri shell has never been compiled: Rust is not installed on the build machine, so `pnpm tauri dev` and `pnpm tauri build` are untested and there is no `Cargo.lock`.
- Not run: the app in a window against a live Portcullis, and WebView2's notification and download behaviour.
- No web push and no offline banner (the PWA code was removed). There is no calendar or games page (the calendar was removed from Citadel in Plan 11).
