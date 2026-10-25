# capabilities/pdf_merger/

Native PDF and image inspection and merging in Armory, with three tools. Files belong to the signed-in account; the internal token never grants access to another account's files.

## Tools

| Tool | Purpose | Connection |
| --- | --- | --- |
| `tool_pdf_inspect` | Inspect selected owned uploads, returning page counts, fresh download links and per-ID failures. Read-only. | Local PDF engine and file store |
| `tool_pdf_listFiles` | List the account's unexpired uploads and merged files with fresh links. Read-only. | Local file store |
| `tool_pdf_merge` | Merge an ordered structured plan into a new PDF. MCP-only; creates a file. | Local PDF engine and file store |

## Slash commands

| Tool | Slash command | Parameters |
| --- | --- | --- |
| `tool_pdf_inspect` | `/pdf inspect` | <ul><li>`file_ids` - required. Comma-separated IDs from chat uploads or the file list; at most 100 per call.</li></ul> |
| `tool_pdf_listFiles` | `/pdf list_files` | No parameters. |

`tool_pdf_merge` takes a structured `plan`, which cannot be expressed by slash command `key=value` inputs. Its `segments` specify file IDs, 1-based PDF page ranges, clockwise rotation and optional image fit. Output options cover filename, title, author, bookmarks, image page size, fit and margins. A PDF page may appear only once in a plan.

## Typical workflow

| Sequence | Tool | Explanation |
| --- | --- | --- |
| 1 | *(manual - no tool)* | Upload PDFs or supported images through Ember chat. |
| 2 | `tool_pdf_listFiles` | Find usable file IDs from the signed-in account. |
| 3 | `tool_pdf_inspect` | Check page counts and IDs before selecting pages. |
| 4 | `tool_pdf_merge` | Submit ordered page segments and output options, then save the returned download link. |
| 5 | `tool_pdf_listFiles` | Renew an expired download link while the stored file still exists. |

## Enable and migrate

The capability ID is `pdf`, displayed as PDF Merger. Restart Armory after installing the shared route/configuration changes, refresh capabilities, and switch PDF online. New capabilities start offline by default. Later tool-only edits can be reloaded with an offline/online cycle; runtime configuration changes require a server restart.

Disable or remove the old `pdf_merger` entry in the deployment's standalone extension configuration to avoid duplicate tools. The real configuration is operator-owned and is not changed by this implementation. The standalone PDFMerger application remains unchanged and may keep running for its own clients.

Ember's existing `/upload/pdf` path now uploads to the native store. It requires the internal token and the account's stable UID. Uploads allow one file of at most 15 MiB, with 64 KiB extra for multipart framing; the whole body is limited while receiving, before disk spooling. Engine file limits and account quotas also apply. Files uploaded after native routing is enabled and files produced by native merges are usable here. Existing standalone IDs are not migrated and must be uploaded again.

## Configuration

Armory settings read its normal environment configuration. Capability tuning lives in `specifics/pdf_merger/configs/config_pdf_merger.json`, with the tracked `.json.example` documenting the shape. Armory's shared config loader copies the example when the real file is absent.

| Setting | Purpose |
| --- | --- |
| `MCP_PDF_MERGER_CONFIG_PATH` | Tuning JSON path; defaults to `specifics/pdf_merger/configs/config_pdf_merger.json`. |
| `MCP_PDF_MERGER_STORE_DIR` | Generated file store; defaults to `specifics/pdf_merger/.data/store`. |
| `MCP_PDF_MERGER_PUBLIC_BASE_URL` | Browser-reachable Armory base URL for download links; defaults to `http://127.0.0.1:{MCP_PORT}`. Configure it for remote browsers or a reverse proxy. |
| `PDF_MERGER_SIGNING_KEY` | Stable HMAC signing secret. If absent, Armory warns and generates an ephemeral key; links stop working after a process restart. |
| `INTERNAL_API_TOKEN` | Authenticates internal requests. Per-account operations refuse missing identity, and PDF operations refuse a non-loopback bind without a token. |

Default tuning keeps files for 6 hours, sweeps every 10 minutes, and signs download links for 60 minutes. Limits cover 100 MiB per engine input file, 500 MiB per account, 50 plan segments, 2,000 output pages, 80 megapixels per image, and two simultaneous merges. The HTTP upload limit still applies first.

`mcp_wait_seconds` must be greater than zero and no more than 100. The job timeout is the smaller of the configured job timeout and this wait. Positive, finite limits and valid expiry intervals are checked before the runtime starts.

## Runtime, storage and downloads

Ember's PDF screen uses fixed internal HTTP adapters on the existing listener.
Every `/pdf/ui` request requires `X-Internal-Token` and `X-Requester-Uid`;
the token never bypasses ownership. Disabled or absent capabilities return 503
before the engine is initialized. These routes add no MCP schemas.

| Method and path | Request / response |
| --- | --- |
| `GET /pdf/ui/files` | Array of native `FileInfo` objects with fresh `download_url` links. |
| `DELETE /pdf/ui/files/{file_id}` | Delete the account's file; returns `{"ok": true}`. |
| `GET /pdf/ui/files/{file_id}/content` | Stream owned PDF/image bytes for preview, with sandbox CSP, nosniff and no-store. |
| `POST /pdf/ui/merge` | Native `MergePlan` body; returns `{"job_id": "..."}` immediately. |
| `GET /pdf/ui/jobs/{job_id}` | `{job_id,state,done,total,result,error}`; state is `queued`, `progress`, `done` or `error`; result is native `MergeResult` on completion, error is `{code,message}` on failure, otherwise null. |
| `POST /pdf/ui/jobs/{job_id}/cancel` | Request cooperative cancellation; returns `{"ok": true}`. Native queue cancellation finishes with `merge_timeout`. |

Uploads continue through `POST /upload/pdf`. UI filenames are plain JSON data;
only MCP results fence filenames for model consumption. Missing and other-owner
files/jobs share the same unavailable response. Expected service failures retain
their native HTTP status and `{error:{code,message}}` body; unexpected failures
return a sanitized 503. Jobs remain in memory and are lost on restart.

`src/capabilities/pdf_merger/utils/pdf_runtime.py` owns one process-wide service on a dedicated event loop. This keeps the file index, quota reservations and job queue on one loop and preserves the service and sweeper across capability reloads. Tool wrappers use `@offload`, so the synchronous wait blocks a worker thread while the engine performs asynchronous work. There is no public job or polling tool.

A merge waits up to the configured deadline and requests cooperative cancellation on timeout. Python worker threads cannot be forcibly killed, so cleanup may finish after the timeout response. A concurrency slot remains occupied until the work actually stops. Shutdown cancels outstanding jobs and waits for cleanup.

Generated state is described in [STATIC-GUIDELINES.md](STATIC-GUIDELINES.md). Application logs use Armory's standard logging; this capability creates no separate cache or log directory.

Signed `/pdf/files/{file_id}/download` URLs are bearer links: anyone holding a valid link can download until the signature or stored file expires. They require no account identity after signature verification. Inspect, list, merge and ordinary file lookup always enforce account ownership; malformed, missing, expired and other-owner file IDs return the same unavailable-file error. Tool result filenames are returned as fenced untrusted data. Stable error types live in `src/capabilities/pdf_merger/utils/pdf_errors.py` so a retained engine and reloaded HTTP/MCP wrappers share the same exception boundary.

## Related vault notes

A later project sync can update `Brain/Projects/MCPServer.md`, the Armory component note, and `Brain/Projects/PDFMerger.md` to describe the native capability and the unchanged standalone application.
