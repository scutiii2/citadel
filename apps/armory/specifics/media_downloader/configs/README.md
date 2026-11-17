# configs

`config_media_downloader.json` is tracked; there is no `.example` twin. Its path can be changed with
`MCP_MEDIA_CONFIG_PATH`. Restart Armory after editing.

| Key | Meaning |
|---|---|
| `file_ttl_hours` | How long a finished download is kept. |
| `sweep_interval_minutes` | How often expired files are removed. |
| `download_link_minutes` | How long a signed download link works. |
| `limits.max_file_mb`, `limits.max_duration_minutes`, `limits.max_session_mb` | Size and length caps for one file and for one account's stored files. |
| `limits.max_concurrent_downloads`, `limits.max_queued_downloads`, `limits.max_caller_downloads` | Parallel, waiting and per-account jobs. |
| `limits.job_timeout_minutes` | A job running longer is stopped. |

The signing key and public address are in `../../../.env` (`MCP_MEDIA_SIGNING_KEY`, `MCP_MEDIA_PUBLIC_BASE_URL`).
Downloads are cache: they are in `.cache/armory/media_downloader/` in the Citadel folder.
