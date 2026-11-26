# Shared files store: one path for every upload

Date: 2026-11-26. Status: design approved in chat, spec under review. Nothing built.

## Why

Every file the user sends goes through Ember, but five different paths handle them:

| File | Path today | Reference the model gets |
|---|---|---|
| PDF, image | Armory `pdf_merger` | `PDFMerger file_id` or `Image file_id` |
| CSV, Excel | text preview, plus Armory `tables` | `table_id` |
| Audio | Scribe | audio header |
| OCR on request | a second upload to Reader | document header |
| Text, code, Word | text preview only, not stored | none |

Tool names and step labels say "PDF" for files that are not PDFs.

## Goal

Armory keeps one store for every upload. Generic file tools list, inspect and view any file. The PDF tools use the same
logic. Scribe and Reader stay unchanged and receive a file only when someone needs a transcript or OCR.

Not in scope: changes to Scribe or Reader, media downloader files, keeping files longer than today, new accepted file
types, and a tool that reads a stored file's text.

## Part 1: the store and the `files` capability

### Store

- A service package in `apps/armory/src/services/user_files/`, built on `session_file_store.py`. The code comes from
  today's `pdf_merger` store, sniffing and download signing.
- It is a service, not a capability, so uploads work whichever capabilities are switched on.
- A record holds: id, owner (account id), name, media type, kind (`pdf`, `image`, `text`, `document`, `table`, `audio`),
  size, page count (PDF and image only), created, expires.
- Accepted: PDF; png, jpg, jpeg, webp, tif, tiff, gif, heic; the plain text and code suffixes of Stronghold's
  `PLAIN_TEXT_SUFFIXES`; docx, xlsx, xlsm; mp3, wav, m4a, ogg, flac, webm. Anything else is refused. PDF and image content is
  checked by sniffing, as today.
- Limits: 15 MB per upload (20 MB audio), 100 MB per stored file (merge results), 500 MB per account, 1 hour life. They
  move to a `files` tuning document in `settings.db`. Merge-only limits stay in `pdf_merger`. Armory Admin's
  Limits page gets a card for the `files` document.
- The signing key and public base URL keep their current environment variable names.

### Routes (Armory)

| Route | Caller | Does |
|---|---|---|
| `POST /upload/file` | Stronghold | stores one file |
| `POST /upload/pdf` | Stronghold | alias of the above for PDF and image |
| `GET /files/{id}/content` | Portcullis, later Stronghold | streams an owned file |
| `GET /files/{id}/download` | signed link | downloads a file |

Existing `/pdf/ui/...` and signed `/pdf/files/...` links keep working. Portcullis serves Ember's image preview from
`/files/{id}/content`, so the preview no longer depends on the `pdf` capability. Ember's URL does not change.
`citadel_auth` gets `/files` in the Portcullis to Armory rule.

### `files` capability

| Tool | Does |
|---|---|
| `tool_files_list` | the account's unexpired files, all kinds, with fresh links |
| `tool_files_inspect` | details and fresh links for chosen ids |
| `tool_files_view` | hidden; returns an image for Legion to show a model. Replaces `tool_pdf_image` |

File logic lives in the shared service, including the image downscaling that moves out of the PDF converter.
`files/domain.py` only turns it into tool results. `tool_pdf_inspect` and `tool_pdf_listFiles` call the same service
filtered to PDF and image. `tool_pdf_merge` reads from the store and writes its result there.
No capability imports another.

### Agents and Legion

- `pdf-assistant`, `data-analyst` and `shared-extensions` allow `tool_files_list` and `tool_files_inspect`.
- `src/runtime/images.py` calls `tool_files_view`.

### Effects

- An administrator must switch `files` on. Until then there are no file tools and no image viewing.
- Files uploaded before the redeploy are not migrated.

## Part 2: one upload route

Ember, Portcullis `POST /api/attachments/file`, Stronghold `POST /attachments/file`, Armory `POST /upload/file`.
Portcullis and Stronghold allow a body large enough for 20 MB in base64 on this path. Permission stays `files.upload`.

The reply has one shape: `file_id`, `filename`, `kind`, `size`, `pages` (optional), `expires_at`, `text`, `char_count`,
`truncated`. Stronghold makes the text preview as it does now.

Reference line:

```
[File file_id: f_… | image | 1 pages | expires_at: …]
```

The `pages` field appears only for PDF and image. Legion image finding, delegation's attachment references and Ember's
image preview read this line and the old `Image file_id` and `PDFMerger file_id` lines.

Ember replaces the per-type branches in `useComposerAttachments.ts` with one call. Nothing visible changes.

Until parts 3 and 4: audio and "Read with OCR" keep their current routes, and for CSV and Excel Stronghold also calls
`/upload/table` so the `table_id` line still appears.

If the store is unavailable and the text is readable, the text is attached without a file id. An image or audio file shows
an error.

The old Portcullis and Stronghold routes stay, so an older installed Ember keeps working.

## Part 3: audio and OCR handoff

Two Stronghold MCP tools:

| Tool | Does |
|---|---|
| `tool_file_transcribe(file_id)` | reads the stored audio, uploads it to Scribe, returns the transcript |
| `tool_file_ocr(file_id)` | reads the stored PDF or image, uploads it to Reader, parses it, returns the text |

- Stronghold uses its existing Scribe and Reader connections. Upload and run go to the same instance.
- It reads `GET /files/{id}/content` as the asking user; Armory checks ownership. `citadel_auth` gets `/files` in the
  Stronghold to Armory rule.
- Results are marked as outside data, not instructions.
- Limits: 20 MB and 120 seconds per request. A longer job fails and says so. A missing connection fails with its reason.
- `shared-extensions` allows `stronghold__tool_file_*`. Ember's instructions send transcription and OCR there.
- Ember uploads audio through the single route and still checks that Scribe is available when audio is attached.
  "Read with OCR" adds an OCR request line instead of uploading the file again.
- The two tools do not expose every Scribe and Reader option. The `scribe__*` tools remain for files held by Scribe.

## Part 4: tables

- The table registry parses a stored file on first use and caches the table in memory. Data and math tools already look
  tables up only there.
- Tools keep the `table_id` parameter and accept a file id in it. Old ids work until they expire.
- Table ownership changes from username to account id.
- Armory parses CSV and xlsx at `/upload/file` and refuses one it cannot read, so a bad file still fails at attach time.
- Ember and agent instructions use the file line instead of the `table_id` line. Stronghold stops calling `/upload/table`.

## Tests

Each part adds tests for its own new logic and runs only those files. Every new read path tests that another account is
refused.

| Part | Test files |
|---|---|
| 1 | Armory: new `test_user_files.py`, `test_pdf_domain.py`, `test_pdf_routes.py`, `test_upload_pdf_route.py`. Legion: `test_images.py`. Portcullis: `test_capability_files.py` |
| 2 | Armory: `test_upload_routes.py`. Stronghold: `test_attachments.py`. Portcullis: `test_attachment_pdf.py`, `test_attachments.py`. Legion: `test_images.py`, `test_delegation.py`. Ember: `ChatInput.test.ts`, `MessageList.test.ts`, `attachments.test.ts` |
| 3 | Stronghold: new `test_mcp_file_tools.py`, `test_tool_services_client.py`. Ember: `ChatInput.test.ts` |
| 4 | Armory: `tests/tables`, `test_upload_table_route.py`, `tests/math/test_tool.py`. Ember: `ChatInput.test.ts` |

## Rollout

| Part | Redeploy |
|---|---|
| 1 | Armory, Armory Admin, Portcullis, Legion |
| 2 | Armory, Stronghold, Portcullis, Legion, Ember |
| 3 | Armory, Stronghold, Legion, Ember |
| 4 | Armory, Stronghold, Legion, Ember |

A change to `citadel_auth` reaches every service that carries a copy. Each part works on its own. An Ember change needs a
rebuilt installer and a live web publish.
