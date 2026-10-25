# Scribe (speech to text) — design

Date: 2026-10-25
Status: implemented; dictation HTTP and composer extension added 2026-10-26

## Goal

Ember users attach an audio file to a chat question and the agent returns its English transcript. An agent calls one tool; the transcript comes back as the tool result. Extension tools have no slash commands, so there is no `/scribe` command in v1. Scribe is its own service, the counterpart of Bard (text to speech, `2026-10-25-bard-design.md`), reached through Armory as an MCP extension.

## Scope

In scope:
- A standalone Python service, `Python/Scribe/`, with its own git repo, venv and port (8091).
- Local transcription with faster-whisper (CPU, model `base.en`, int8), English only.
- Audio decoding with ffmpeg; accepted formats mp3, wav, m4a, ogg, flac, webm.
- One MCP tool, `tool_scribe_transcribe`.
- Per-account audio uploads with a time-to-live and a quota; a transcript cache.
- An ember_api upload route and an ember_web attachment path for audio files.
- Microphone dictation into Ember's editable chat draft, through the same Scribe service.
- Registration as an Armory extension.

Out of scope (can be added later without changing this design):
- Streaming and WebSocket input.
- Speaker labels, translation, other languages, other engines (the engine sits behind an interface).
- A transcript download link or a standalone Scribe web page.
- A Scribe audit log, admin-managed models (Bard's voice download and delete).

## Decision: separate service, Armory extension

Same reasoning as Bard: a heavy native dependency (CTranslate2, the Whisper model) and CPU-bound work should not share a process with Armory or with Piper, and the service may later move to a GPU machine. Scribe copies Bard's small scaffolding (config, errors, identity, middleware, store, run) instead of importing it; the two repos stay independent.

```
ember_web ──POST /api/attachments/audio──► ember_api ──POST /api/files──► Scribe :8091
agent ──tools/call──► Armory (/mcp proxy, extension "scribe") ──► Scribe :8091/mcp
```

Audio reaches Scribe only through ember_api, which hides Scribe's origin, applies permissions and logs the action, as `/api/attachments/pdf` does for PDFMerger. The agent never fetches audio by URL.

## Scribe service

### Layout

```
Python/Scribe/
  AGENTS.md, CLAUDE.md (@AGENTS.md), README.md, pyproject.toml, .env.example, .gitignore, Dockerfile, docker-compose.yml
  src/ config.py errors.py contract.py engine.py store.py service.py identity.py middleware.py app.py run.py
  tests/
  .data/                (gitignored)  models/  audio/
```

### Components

| Unit | Responsibility |
| --- | --- |
| `config.py` | `Settings` from environment (`SCRIBE_*`, `INTERNAL_API_TOKEN`); `exposed_without_token`. |
| `engine.py` | `SttEngine` protocol and `WhisperEngine`. `decode(path)` runs ffmpeg through an async subprocess and returns 16 kHz mono s16le PCM in memory (its length is the duration); `transcribe(pcm)` runs faster-whisper in a worker thread on a numpy array. No temp wav exists. |
| `store.py` | `AudioStore`: uploads and transcripts per owner, deterministic ids, time-to-live, quota, atomic writes. |
| `service.py` | `ScribeService.upload` / `transcribe`: validate, store, cache lookup, transcribe under a semaphore (default 1). One lock per (owner, file id) so identical concurrent requests transcribe once. |
| `identity.py` | `owner_from_context`: the asking user's name from `_meta.requester.username`. |
| `middleware.py` | `InternalTokenMiddleware`: `X-Internal-Token` on `/mcp` and `/api`. |
| `app.py` | `build_app(settings, engine=None)`: FastMCP tool, `POST /api/files`, `GET /health`. |
| `run.py` | `python -m src.run`: refuses to start exposed without a token, then runs uvicorn. |

### Tool

The result model ends with `message`, as Armory's contract rules require.

| Tool | Arguments | Result |
| --- | --- | --- |
| `tool_scribe_transcribe` | `file_id` (required), `timestamps` (optional, default false) | `text`, `duration_s`, `language` (`"en"`), `segments` (only with `timestamps`: `start_s`, `end_s`, `text`), `cached`, `message` |

It carries `meta={"keywords": ["transcribe", "speech to text", "stt", "audio", "dictation"], "display_label": "Transcribing audio"}`. Extension tools reach clients namespaced as `scribe__tool_scribe_transcribe`.

### Files and cache

- Upload id is `sha256(owner + NUL + audio bytes)[:32]`, hex: stable, so re-uploading the same file is a no-op.
- Files live in `.data/audio/<sha256(owner)[:16]>/<file_id>.bin` with a `<file_id>.json` sidecar (`filename`, `size_bytes`, `duration_s`, `created_at`). The transcript is cached beside it as `<file_id>.<model>.json`; the model name in the key stops a model change from serving stale text.
- Expiry is by `created_at` (default 24 hours). `get` deletes an expired file; `put` removes the owner's expired files first; startup sweeps everything. There is no background sweeper.
- Quota per owner (default 200 MB); a write that would exceed it fails with `quota_exceeded`.
- Each id is checked against `^[0-9a-f]{32}$` before any path is built. Another owner's file, a missing file and a malformed id all answer "not found".

### HTTP

- `POST /api/files`: raw audio bytes as the body, `X-Requester-Username` (missing header is 401) and `X-Filename`. Answers `{file_id, duration_s, size_bytes, expires_at}`. Rejects with 413 over `SCRIBE_MAX_BYTES` (default 25 MB), 400 for a format ffmpeg cannot read, 400 over `SCRIBE_MAX_SECONDS` (default 150).
- `GET /health` returns `{"ok": true}` and needs no token.

Validation is by ffmpeg probe, not by file name or declared type. The duration check runs at upload, so a too-long file fails in the attachment chip, not later in the agent's tool call.

### Concurrency and limits

- One transcription at a time by default (`SCRIBE_CONCURRENCY`); the others wait on the semaphore. Every blocking call (model, file IO) runs through `asyncio.to_thread`; ffmpeg runs as an asyncio subprocess.
- Transcription is bounded by `SCRIBE_TIMEOUT_S`; a timeout fails with `engine_failed` (default 110 s, under Armory's 120 s call timeout).
- Measured on this machine (Ryzen 7 7445HS, 6 cores, int8, beam 1): `small.en` ran at x0.5 real time and `base.en` at x1.6. Defaults are therefore `base.en`, 150 s of audio and a 110 s timeout, so a full-length file finishes inside the call budget. Raise model and caps together on a faster or GPU host; an async job design was considered and left out of v1.

### Auth and identity

Same as Bard: with `INTERNAL_API_TOKEN` set, `/mcp` and `/api/*` need a matching `X-Internal-Token` (constant-time compare); `run.py` exits when `SCRIBE_HOST` is not loopback and the token is empty; Armory forwards `_meta.requester` when the extension entry sets `forward_requester`; the owner key is the username; a tool call with no username fails with `identity_required`.

### Errors

`ScribeError` subclasses carry a stable `code`: `audio_rejected`, `file_not_found`, `quota_exceeded`, `engine_failed`, `identity_required`. The tool layer turns them into `ToolError` with the message; the message never contains a filesystem path.

## Armory registration

An entry in `apps/armory/configs/config_extensions.json.example` (and, by the operator, the real `config_extensions.json`):

```json
"scribe": {
  "label": "Scribe",
  "description": "Speech to text: transcribes an attached audio file to English text.",
  "url": "http://127.0.0.1:8091/mcp",
  "headers": { "X-Internal-Token": "${INTERNAL_API_TOKEN}" },
  "forward_requester": true
}
```

Armory handshakes with each extension at startup, so Scribe must be running first; an unreachable Scribe marks only that extension as errored.

## ember_api

- `POST /api/attachments/audio` in `routes/attachments.py`: body `AttachmentIn` (base64 JSON, as every POST to ember_api; see `json_only.py`), permission `files.upload`, 413 over 20 MB (`MAX_FILE_BYTES` is 15 MB today, so the audio route has its own `AudioIn` model and limit; 20 MB, not Scribe's 25 MB, because base64 of 25 MB would not fit the request cap for `/api/attachments`). Suffix check: `.mp3 .wav .m4a .ogg .flac .webm`. It forwards the bytes to `POST {scribe_url}/api/files` with the account's identity headers and the internal token, logs `attachments.audio` through `LogWriter`, and answers `{filename, file_id, duration_s, expires_at}`.
- A small `ScribeGateway` service (httpx, like `CapabilityFilesGateway`) does the forward; Scribe errors map to 400 for rejected audio and 502 for an unreachable Scribe or a refused internal token.
- New setting `scribe_url` (default `http://127.0.0.1:8091`).

## ember_web

- `utils/content/attachments.ts` gets `AUDIO_FILE` (the suffix regex) beside `PDF_FILE` and `TABLE_FILE`.
- `api/files/AttachmentsClient.ts` gets `audio(file)` posting to `/api/attachments/audio`.
- `useComposerAttachments.ts` routes audio files to `attachmentsClient.audio` and folds a header line into the question, in the same style as the PDF header:
  `[Audio file_id: <id> | <duration> s | expires_at: <ts> | call scribe tool_scribe_transcribe with this file_id to get the transcript]`
  There is no text preview, so the chip shows the file name and duration.
- `ChatAttachment.vue` needs no change: only image headers get special rendering; any other attachment, the audio header included, shows as a collapsed block with its text. `splitAttachments` handles the restore-on-edit path as it does for PDFs.
- No new component: the transcript is the tool result and the generic formatter shows `message` first.

Per `AGENTS.md`: no reduced-motion setting, media query or test.

## Testing

### Dictation extension (2026-10-26)

`POST /api/transcribe` accepts raw audio with the same identity headers, internal-token middleware and error mapping as `/api/files`. It calls `ScribeService.upload`, then `transcribe(owner, file_id, False)`, and returns `{text, duration_s}`. Cache, quota, semaphore, 25 MB service limit and 150 s duration limit stay in force. Invalid audio is 400, byte/quota excess 413, missing identity/token 401 and engine failure 503.

Ember's `POST /api/attachments/dictate` uses `AudioIn`, the same suffix/base64/20 MB checks as `/audio`, and `files.upload`. `ScribeGateway.transcribe` supplies the signed-in identity and internal token. The route logs `attachments.dictate` with byte count only and returns `{text, duration_s}`. Audio rejection and quota remain 400/413; connection, service and internal-auth failures become 502.

`attachmentsClient.dictate(blob, signal?)` sends WebM as base64 JSON. `features/chat/composables/useDictation.ts` owns the recorder, microphone tracks, 150 s auto-stop timer and abort controller. States are idle, recording, transcribing and error. A second click stops recording. `ChatInput.vue` appends the transcript through its existing draft insertion helper; it does not send it. The microphone appears beside Attach with `files.upload` and WebM MediaRecorder support, pulses while recording and displays status and inline permission/service errors. Cancellation, account/chat changes, deactivation and disposal stop tracks and suppress late responses.

Tests cover the HTTP route/cache/errors, Ember proxy permissions/validation/audit, client limits and recorder lifecycle. Chrome speech tests capture WebM and verify editable draft insertion at desktop, 768 and 375 widths with a fake API; live model accuracy is a separate service check.

- Scribe unit tests with a fake engine: config, store (hit, miss, expiry, quota, id validation, owner isolation), service (cache, concurrency, errors, duration cap), HTTP route and middleware.
- Engine tests that need ffmpeg or the real model skip when those are missing.
- One MCP handshake test against a real uvicorn server on a free port: upload a short wav over HTTP, list tools, call `tool_scribe_transcribe` with `_meta.requester`.
- ember_api: route tests with the existing `upstream` fake (identity headers, error mapping, size and suffix limits, login and permission required).
- ember_web: vitest for `AUDIO_FILE` and the `audioHeader` line.
- Armory: a test that the example extension config parses and contains `scribe`.

## Risks and open points

- faster-whisper 1.2.1 installs and runs on Python 3.14 on this Windows machine (real transcription verified end to end).
- asyncio subprocesses need the Proactor event loop on Windows. uvicorn's default loop works; `--reload` would not.
- `base.en` is downloaded on first use (about 150 MB), not committed. Pre-download it in the Docker build or a `scripts` step so the first request does not stall; check the model licence before redistribution.
- Concurrency defaults use the measurements above. A live WebM dictation browser check passed on 2026-10-26 using cached `base.en`, an isolated HTTP server and generated microphone speech. Physical microphone accuracy remains a device check.
- Stale `pdf_merger` and `media_downloader` entries remain in `config_extensions.json.example`. Not changed here.
- Uploads hold user audio for 24 hours on the Scribe machine; the docs must say so.
