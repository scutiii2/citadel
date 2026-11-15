# Plan 9: Ember Windows app

Branch: `feat/ember-windows`.

## Result

- `apps/ember`: copy of `ember_web` (src, public, configs; no Dockerfile, nginx, e2e or PWA). Port 26506 for the browser dev server.
- Configurable server: `src/utils/server.ts` holds the Portcullis URL (entered on the login page), the session token, and helpers used by `apiRequest`, the turn event stream, the MCP client, the share dialog, the admin link, image attachments and Bard audio.
- Portcullis (tests added in `tests/test_auth.py`):
  - `session_token()` in `deps.py`: cookie first, else `Authorization: Bearer`. Used by `current_account`, logout and password change.
  - `POST /api/auth/login` with `X-Ember-Client: desktop` answers with `session_token` too (`DesktopLoginOut`); browsers never get it.
  - CORS for `desktop_origins` (default the three Tauri origins), no credentials, so cookies still never cross origins.
- `src-tauri/`: Tauri 2 config (NSIS per-user installer, CSP, `core:default` only), Cargo manifest, `main.rs`, icons from `icon-512.png`.

## Decisions

1. **Token auth, not cookies.** The cookie is SameSite=Strict, and a cross-origin app would need SameSite=None over HTTPS. A bearer works over plain LAN HTTP too. The token is the same session token, so logout and "log out other sessions" work unchanged.
2. **Web push: none.** `ember_web` never had it. Native notifications are a later step.
3. **Shared-chat links** keep the `<server>/shared/<token>` form, but nothing serves that page now. Needs a small Portcullis-rendered read-only page later.
4. **Games and calendar:** `ember_web` had neither page, so there was nothing to copy. The calendar API exists in Stronghold; a view is future work.
5. **PWA removed** (service worker, manifest, offline banner).

## Not done

- The Tauri shell was never compiled: Rust is not installed here. `pnpm tauri dev` and `pnpm tauri build` are untested, and no `Cargo.lock` exists yet.
- Not run: the app in a window or browser against a live Portcullis.
- Still broken in the Windows app: live dictation, PDF merger and media downloader file links, chat download links (see `apps/ember/README.md`).
- Playwright e2e were not copied.

## Execution notes (2026-11-16)

- `apps/ember`: vue-tsc clean, vitest 2210 passed (181 files).
- Portcullis: 1319 passed.
