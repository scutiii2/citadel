# ember

Project note: `Brain/Projects/ember.md` in the Obsidian vault (`../../../../Brain/` from this folder), once it exists.

Ember Windows app: Vue 3 + TypeScript UI copied from `ember_web` (Plan 9) inside a Tauri 2 shell (`src-tauri/`). It talks only to Portcullis, at the address the user enters. Follow the `ember-frontend-design` and `ember-design-system` skills.

## Rules
- Never call `fetch` or build an `/api` URL by hand: use `apiRequest`, or `apiUrl`, `authHeaders` and `credentialsMode` from `src/utils/server.ts`. Use `mediaUrl` for `<img>` and `<audio>` sources. The browser build and the Windows app differ only there.
- `ember_web` is reference only. Do not copy fixes back and forth; this app is the maintained one.
- Radius only through `--radius-*` tokens. Never add reduced-motion code.
- Checks: `pnpm exec vue-tsc -b`, `pnpm test`. The Tauri shell needs Rust and was not built when written.
