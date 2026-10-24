# Bard (text to speech) — design

Date: 2026-10-25
Status: design approved in chat, awaiting written-spec review

## Goal

Ember users and agents can turn text into spoken English. An agent calls one tool; the answer shows an in-chat audio player and a download link. Extension tools have no slash commands, so there is no `/bard` command in v1. Bard is its own service, reached through Armory as an MCP extension.

## Scope

In scope:
- A standalone Python service, `Python/Bard/`, with its own git repo, venv and port (8090).
- Local synthesis with Piper (CPU), one English voice, MP3 output through ffmpeg.
- Two MCP tools: `tool_bard_speak`, `tool_bard_listVoices`.
- Per-account audio files with a cache, a time-to-live and a quota.
- An ember_api route that streams a stored audio file to the browser.
- An in-chat audio player with a download link in ember_web.
- Registration as an Armory extension.

Out of scope (decided, can be added later without changing this design):
- Streaming audio while it is synthesized, and WebSocket output.
- Voice cloning, other languages, other engines (the engine sits behind an interface).
- A standalone Bard web page.
- A Bard audit log.
- Browser-direct links to port 8090 (see "Playback path").

## Decision: separate service, Armory extension

`pdf_merger` and `media_downloader` used to be standalone extensions and are now Armory capabilities; they are the wrong template. The extension mechanism itself is unchanged (`apps/armory/src/services/extensions.py`, entries in `configs/config_extensions.json`), and `apps/armory/src/_fixtures/reference_extension_server.py` is the reference for a standalone FastMCP server.

Bard stays separate because it carries a heavy native dependency (the Piper model and ONNX runtime) and CPU-bound work that should not share a process with Armory's request handling, and because it may later move to a GPU machine.

```
ember_web ──/api/bard/audio/{id}──► ember_api ──GET /api/files/{id}──► Bard :8090
agent ──tools/call──► Armory (/mcp proxy, extension "bard") ──► Bard :8090/mcp
```

## Bard service

### Layout

```
Python/Bard/
  AGENTS.md, CLAUDE.md (@AGENTS.md), README.md, pyproject.toml, .env.example, .gitignore
  src/ config.py errors.py text_prep.py contract.py engine.py store.py service.py identity.py middleware.py app.py run.py
  tests/
  .data/                (gitignored)  voices/  audio/
```

### Components

| Unit | Responsibility |
| --- | --- |
| `config.py` | `Settings` from environment (`BARD_*`, `INTERNAL_API_TOKEN`); `exposed_without_token`. |
| `text_prep.py` | `prepare(text, max_chars)`: strips Markdown, collapses whitespace, rejects empty or too long text. |
| `engine.py` | `TtsEngine` protocol and `PiperEngine`. Piper runs in a worker thread; ffmpeg encodes MP3 through an async subprocess. |
| `store.py` | `AudioStore`: files per owner, deterministic id, time-to-live, quota, atomic writes. |
| `service.py` | `BardService.speak` / `list_voices`: prepare, cache lookup, synthesize under a semaphore, store. One lock per (owner, file id) so identical concurrent requests synthesize once. |
| `identity.py` | `owner_from_context`: the asking user's name from `_meta.requester.username`. |
| `middleware.py` | `InternalTokenMiddleware`: `X-Internal-Token` on `/mcp` and `/api`. |
| `app.py` | `build_app(settings, engine=None)`: FastMCP tools, `GET /api/files/{id}`, `GET /health`. |
| `run.py` | `python -m src.run`: refuses to start exposed without a token, then runs uvicorn. |

### Tools

Result models end with `message`, as Armory's contract rules require, so ember's generic formatter shows it first.

| Tool | Arguments | Result |
| --- | --- | --- |
| `tool_bard_speak` | `text` (required, at most `BARD_MAX_CHARS`), `voice` (optional, one of the listed voices) | `file_id`, `voice`, `duration_s`, `size_bytes`, `cached`, `message` |
| `tool_bard_listVoices` | none | `voices`, `default`, `message`. Declares `readOnlyHint`. |

Both carry `meta={"keywords": [...], "display_label": "..."}`. Extension tools reach clients namespaced as `bard__tool_bard_speak` (separator `__`, `NAMESPACE_SEPARATOR` in `extensions.py`).

### Files and cache

- File id is `sha256(voice + NUL + prepared text)[:32]`, hex. It is stable, so a repeat request is a cache hit.
- Files live in `.data/audio/<sha256(owner)[:16]>/<file_id>.mp3` with a `<file_id>.json` sidecar (`voice`, `duration_s`, `created_at`).
- Expiry is by `created_at` (default 24 hours). `get` deletes an expired file; `put` removes the owner's expired files first; startup sweeps everything. There is no background sweeper.
- Quota per owner (default 200 MB); a write that would exceed it fails with `quota_exceeded`.
- Each id is checked against `^[0-9a-f]{32}$` before any path is built. Another owner's file, a missing file and a malformed id all answer "not found".

### HTTP

- `GET /api/files/{file_id}` serves the owner's MP3 (`audio/mpeg`, range requests, `Cache-Control: private, no-store`, `nosniff`). The owner comes from `X-Requester-Username`; a missing header is 401.
- `GET /health` returns `{"ok": true}` and needs no token.

### Auth and identity

- With `INTERNAL_API_TOKEN` set, `/mcp` and `/api/*` require a matching `X-Internal-Token` (constant-time compare).
- `run.py` exits when `BARD_HOST` is not loopback and the token is empty.
- Armory forwards `_meta.requester` (`username`, `email`) when the extension entry sets `forward_requester`. Armory does not forward the account uid to extensions, so Bard's owner key is the username. A renamed account would lose access to its earlier files, which only live a day. Revisit if Armory starts forwarding `uid`.
- A tool call with no username fails with `identity_required`.

### Errors

`BardError` subclasses carry a stable `code`: `text_rejected`, `quota_exceeded`, `voice_unavailable`, `engine_failed`, `identity_required`. The tool layer turns them into `ToolError` with the message; the message never contains a filesystem path.

## Armory registration

An entry in `apps/armory/configs/config_extensions.json.example` (and, by the operator, the real `config_extensions.json`):

```json
"bard": {
  "label": "Bard",
  "description": "Text to speech: turns text into an MP3 and plays it in chat. English voice.",
  "url": "http://127.0.0.1:8090/mcp",
  "headers": { "X-Internal-Token": "${INTERNAL_API_TOKEN}" },
  "forward_requester": true
}
```

Armory handshakes with each extension at startup, so Bard must be running first; an unreachable Bard marks only that extension as errored.

## Playback path

ember_web's content security policy is `default-src 'self'` with no `media-src` (dev `vite.config.ts` and `nginx.conf`), so an `<audio>` element cannot load a file from port 8090. Audio therefore goes through ember_api, like the PDF and video workspaces:

- `GET /api/bard/audio/{file_id}` in ember_api. Requires the `tools.execute` and `files.download` permissions. Streams `GET {bard_url}/api/files/{file_id}` with the account's identity headers and the internal token, forwarding `Range`, and never exposes Bard's origin.
- New ember_api setting `bard_url` (default `http://127.0.0.1:8090`).

## ember_web

`toolResultFormat.ts` skips the `download_url` key and shows `message`, so the result needs no formatter change. A new `BardAudio.vue` renders an `<audio controls preload="none">` plus a "Download MP3" link, both on `/api/bard/audio/{file_id}`. The link is shown only with the `files.download` permission, as in the media downloader's file rows. `MessageList.vue` shows one `BardAudio` per successful step whose tool name ends in `tool_bard_speak` and whose result JSON has a string `file_id` (helper `bardFileIds` in `utils/tools/bardAudio.ts`), directly under the tool steps, for saved and live answers. It sits outside `ToolSteps.vue` on purpose: finished answers collapse their tool steps into one line, and the player must be visible without expanding it. The tool name is matched by suffix, so the player does not depend on the namespace separator.

Per `AGENTS.md`: no reduced-motion setting, media query or test.

## Testing

- Bard unit tests with a fake engine: text preparation, configuration, store (hit, miss, expiry, quota, id validation, owner isolation), service (cache, concurrency, errors), HTTP routes and middleware.
- Engine tests that need ffmpeg or a real Piper voice skip when those are missing.
- One MCP handshake test against a real uvicorn server on a free port: list tools, call `tool_bard_speak` with `_meta.requester`, fetch the file over HTTP.
- ember_api: route tests with the existing `upstream` fake (Range forwarded, identity headers, error mapping, login and permission required).
- ember_web: component and `ToolSteps` tests with vitest.
- Armory: a test that the example extension config parses and contains `bard`.

## Risks and open points

- Piper and ffmpeg on this Windows machine: `piper-tts==1.8.0` installs and imports on Python 3.14 here, and ffmpeg is on PATH; a real synthesis has not been run yet (plan Task 1 does it first).
- asyncio subprocesses need the Proactor event loop on Windows. uvicorn's default loop works; `--reload` would not.
- Range support relies on Starlette's `FileResponse`; a test pins it.
- Stale `pdf_merger` and `media_downloader` entries remain in `config_extensions.json.example`. Not changed here.
- The default voice file (`en_US-lessac-medium`) is downloaded, not committed; check its licence before any redistribution.
