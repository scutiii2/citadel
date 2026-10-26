# Media downloader (`capabilities/media_downloader/`)

Six native armory tools probe public videos, music and photos, build grouped ZIP packages, queue downloads, poll progress and list unexpired files. The existing `video` capability ID, `/video` commands, `tool_media_*` names, routes and storage paths remain compatible. See [capability conventions](../README.md).

Direct image URLs (including extensionless URLs), single TikTok photo posts,
Instagram posts and Pinterest pins offer the `photos` preset. One photo stays
in its original raster format; multiple photos become a ZIP with ordered,
numbered filenames. Probe responses include `photo_count` (zero for video or
music); photo files have `kind: "photo"` and an image or `application/zip` MIME.
At most 100 photos are accepted per post. Profiles, boards and playlists are
refused. Site access still depends on anonymous availability: private posts,
login requirements, challenges and unavailable content can fail. No cookies
or account credentials are imported. Video options and MP3/M4A music remain
handled by yt-dlp; gallery-dl discovers photo URLs only.

## Tools

| Tool | Purpose | Connection |
| --- | --- | --- |
| `tool_media_probe` | Inspect public media and its unblocked download options | Public HTTP(S) |
| `tool_media_download` | Queue a download and return a job id immediately | Public HTTP(S), local FFmpeg |
| `tool_media_status` | Poll your job and get a fresh signed link | Local queue |
| `tool_media_listFiles` | List your unexpired files with fresh signed links | Local store |
| `tool_media_package` | Create a group, add/remove media, or start its locked ZIP download | Public HTTP(S), local queue/store |
| `tool_media_packages` | List groups or inspect package items, failures and fresh ZIP links | Local queue/store |

## Slash commands

| Tool | Slash command | Parameters |
| --- | --- | --- |
| `tool_media_probe` | `/media probe` | <ul><li>`url` - required. Public video, music, direct image or single photo-post URL.</li></ul> |
| `tool_media_download` | `/media download` | <ul><li>`url` - required. Public media URL.</li><li>`preset` - optional, default `best`. Choose an unblocked preset from probe; use `photos` for images and photo posts.</li></ul> |
| `tool_media_status` | `/media status` | <ul><li>`job_id` - required. Job id returned by download.</li></ul> |
| `tool_media_listFiles` | `/media files` | No parameters; account comes from authenticated request context. |
| `tool_media_package` | `/media package` | <ul><li>`action` - required. `create`, `add`, `remove` or `start`.</li><li>`package_id` - optional, default empty. Required except for create.</li><li>`name` - optional, default empty. Required for create.</li><li>`urls` - optional, default empty. Comma-separated URLs for add; percent-encode commas inside URLs.</li><li>`preset` - optional, default `best`. Shared preset for added links.</li><li>`item_id` - optional, default empty. Required for remove.</li></ul> |
| `tool_media_packages` | `/media packages` | <ul><li>`package_id` - optional, default empty. Inspect one group; omit to list your groups.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
| --- | --- | --- |
| 1 | `tool_media_probe` | Inspect the URL and choose an unblocked preset. |
| 2 | `tool_media_download` | Start the download; retain its job_id. |
| 3 | `tool_media_status` | Poll until done or error, then open the signed download_url. |
| 4 | `tool_media_listFiles` | Find earlier unexpired files or renew a download link. |
| 5 | `tool_media_package` | For packages: create a named draft, add media with chosen presets, then start. |
| 6 | `tool_media_packages` | Inspect progress and per-item failures; get the ZIP link when complete. |

## Download groups and packages

Groups are account-owned drafts. Add URLs with a preset and remove individual
items while in draft. An accepted start atomically locks membership and creates
one job; queued, downloading, completed, failed and cancelled packages remain
locked. A full queue leaves the draft editable. URL validation rechecks the lock
after yielding, so a concurrent start cannot admit a late item.

One package occupies one existing queue slot and downloads items sequentially.
Successful files become a numbered ZIP (`kind: package`); photo carousels retain
their inner ZIP. Ordinary site failures are recorded per item and remaining
links continue. A package with no successful items fails. Cancellation, size and
storage limit failures stop the job. Member and combined payload sizes, final
ZIP size and account storage all respect existing limits. Scratch members are
removed after archiving; only the final ZIP enters the file list.

Each account can hold 20 groups with up to 50 media links each. Drafts and
finished history expire on the existing file TTL sweep; active packages remain
until finished. Groups and job history live in process memory and are lost on
restart. Completed ZIPs persist with existing file sidecars and TTL.
Restart Armory and ember_api after deploying the new HTTP adapters.

## Configuration and operation

Enable `media` on armory's Capabilities page after Refresh (or `POST /capabilities/refresh`, then `PATCH /capabilities/media` with `{"enabled": true}`). A fresh install leaves it offline. `/media help` uses the adjacent `help.json`. Toggle `media` offline to hide tools and refuse new signed HTTP downloads; already running jobs finish and expire normally. Shared HTTP/runtime changes require an armory restart on deployment.

Caps and TTLs use `specifics/media_downloader/configs/config_media_downloader.json.example`; the existing app config loader copies it to `config_media_downloader.json` on first use. The shape preserves `file_ttl_hours`, `sweep_interval_minutes`, `download_link_minutes` and the original `limits` keys (file MB, duration minutes, session MB, concurrency, queue size and job timeout minutes). `limits.max_caller_downloads` additionally bounds each account's unfinished jobs, default 2. All caps and intervals must be positive, except the queued-job allowance may be zero.

Settings in `src/config.py` accept `MCP_MEDIA_STORE_DIR` (default `specifics/media_downloader/.data/store`), `MCP_MEDIA_LOG_DIR` (reserved log location), `MCP_MEDIA_CONFIG_PATH`, `MCP_MEDIA_PUBLIC_BASE_URL` and `MCP_MEDIA_SIGNING_KEY`. Paths follow armory's working directory convention. Set the public base URL to the externally reachable armory origin (including any proxy path prefix); the fallback is `http://127.0.0.1:<MCP_PORT>`. A persistent random signing key keeps old links valid across restarts; absent a key, a process-local random key is used and restart invalidates old links. `MCP_HOST`, `MCP_PORT` and `INTERNAL_API_TOKEN` retain their existing armory meaning.

Install armory's dependencies, including pinned `yt-dlp[default,curl-cffi]==2026.8.19` and `gallery-dl==1.32.17`. FFmpeg must be on PATH for video/music; photos work without it. Missing FFmpeg refuses video/music probe/download with `ffmpeg_missing`, while photos, server startup and file/status reads remain available. DRM, login-only media, live streams and playlists are refused. The configured download cap is rechecked against extraction and actual bytes; concurrent commits reserve account storage. For carousels the file cap covers the combined photos and final ZIP; cancellation and account quotas still apply.

## File serving decision

Ember's Media Downloader screen uses fixed internal HTTP adapters on this same
listener. Every `/media/ui` call requires `X-Internal-Token` and
`X-Requester-Uid`. Only that UID owns the files and jobs; the token does not
grant cross-account access. Disabled or absent capabilities return 503 before
initializing the runtime. No extra MCP tool schemas are exposed.

| Method and path | Request / response |
| --- | --- |
| `POST /media/ui/probe` | `{url}`; returns native `ProbeResult`, with plain metadata. |
| `POST /media/ui/downloads` | `{url,preset}`; returns `{"job_id":"..."}` immediately. |
| `GET /media/ui/jobs/{job_id}` | Native `JobStatus`, including fresh signed file link on completion. |
| `POST /media/ui/jobs/{job_id}/cancel` | Request cooperative cancellation; returns `{"ok":true}`. Polling eventually reports `error` with code `cancelled`. |
| `GET /media/ui/files` | Array of native `FileInfo` objects with fresh signed links. |
| `DELETE /media/ui/files/{file_id}` | Delete an owned file; returns `{"ok":true}`. |
| `GET /media/ui/packages` | List owned groups, items and current job snapshots. |
| `POST /media/ui/packages` | `{name}`; create an editable draft. |
| `GET /media/ui/packages/{package_id}` | Inspect an owned group and fresh ZIP link. |
| `POST /media/ui/packages/{package_id}/items` | `{url,preset}`; append to an editable draft. |
| `DELETE /media/ui/packages/{package_id}/items/{item_id}` | Remove a draft item. |
| `POST /media/ui/packages/{package_id}/start` | `{}`; atomically lock and queue; returns `{job_id}`. |

Probe and download retain the service's URL policy and network guards. Video
and music require FFmpeg; photos do not. Missing and other-owner IDs return
the same unavailable response. Expected service errors retain their native
HTTP status and `{error:{code,message}}` body. Unexpected failures return a
sanitized 503. These adapters share the existing runtime, quotas and queue.

Signed links use `GET /media/files/{file_id}/download?exp=...&sig=...` on armory's existing listener. `command_routes.install_command_routes` installs the route and wraps the existing lifespan for cleanup; no new port or service is started. The route checks the capability toggle and exposure policy before initializing anything, validates the HMAC and expiry, then checks file TTL. Missing, expired and invalid links return the same 404. Starlette FileResponse provides streaming and Range support with attachment disposition, nosniff, no-store and no-referrer headers.

Links are bearer credentials: anyone holding a valid link can download until link/file expiry, without an account header. Do not log or expose their query strings at a proxy. HTTPS is required at the public edge to protect links in transit. The standalone HMAC format is retained; listing or polling a completed job mints fresh links without changing the stored file.

## Background work and state decision

The existing async JobQueue remains the owner of concurrency, progress, cooperative cancellation and timeouts. It runs on one dedicated background event loop in process-owned `capabilities/media_downloader/utils/media_downloads.py`, so an offloaded tool can return a job id without destroying its task. yt-dlp uses worker threads; the tool does not wait for a download. The TTL sweeper shares the background loop. Shutdown cancels queued/running jobs cooperatively and drains the loop and worker executor. Blocking worker cancellation can take up to its socket timeout, or longer during a blocked local FFmpeg operation; Python cannot kill the thread safely.

No JobWatcher is needed: the job is local work already owned by the queue. Jobs are in memory and do not resume after a process restart. Stored file sidecars rebuild the index; startup removes orphan files and scratch directories. The runtime and guard-bearing `utils` modules persist through capability tool reloads, retaining the same queue, store and network patches. Updating these engine modules requires an armory restart; tool/contract/domain/help changes may be reloaded. Runtime data stays under capability specifics, never under source. There is no separate audit database or email notification flow; operational logging uses armory's existing logger.

## Identity, read-only declarations and SSRF

Account identity comes from `current_uid()` and `current_username()` through armory's trusted request context; it is never a tool argument. Only the stable UID scopes files, jobs and quotas. A missing UID refuses the call, and `is_exposed_without_token` refuses all calls and signed-file serving on a non-loopback tokenless bind. Authenticated upstream callers must be trusted to supply truthful identity, as with armory's other per-account capabilities. No privileged cross-account MCP access is carried over from the standalone service.

Probe, status and listFiles declare read-only: they inspect remote metadata or existing local records and generate URLs; they do not enqueue a job, commit a file, or change user records. Infrastructure initialization and background TTL maintenance are independent of these read operations. Download changes disk/network state and never declares read-only. Web titles, uploaders and file names are capped and fenced with `services/untrusted.py` before reaching the model.

The port retains URL validation and socket/curl guards: only public globally routable addresses on ports 80/443, checking redirect targets, pinning curl DNS answers, disabling proxies and refusing external network downloaders. FFmpeg is allowed only for local postprocessing. Browser impersonation fails closed if dependency internals no longer satisfy guard checks. Run the guard regression tests before changing the dependency pin. These guards patch shared libraries process-wide but activate per thread; unrelated armory requests are unaffected.

## Migration boundaries

The standalone MediaDownloader service and Vue web app are not migrated or removed; standalone browser files remain separate. When the native capability is enabled, disable or remove only the `media_downloader` extension entry in armory's `configs/config_extensions.json` through the existing extension controls to avoid duplicate tools. This change does not alter that deployment config. Deferred playlists, cookies, subtitles, history and clipping remain out of scope.

Tests use fake extractors or synthetic localhost fixtures with explicitly permissive test guards, never a real website download. Tests cover policies, guards, presets, store quotas/TTL/restart, sanitizing, signing, queue lifecycle/errors, identity scoping, signed streaming, dynamic loading, help and tool annotations.
