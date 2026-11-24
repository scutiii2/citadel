# Armory settings

Armory keeps its listener and Treasury bootstrap address in tracked `configs/config_app.json`. What an administrator can change is saved in `.data/armory/settings.db` in the Citadel
folder (see `src/services/settings_store.py`) and edited on the pages of Armory Admin. `.env` and the built-in defaults
give the starting value; a value saved on a page wins. Secrets are write-only: a page says whether one is set and never
shows it.

| Page | Table | What it holds |
|---|---|---|
| Capabilities | `capabilities` | Which capabilities are on. Every capability starts off. A capability with no entry is never loaded. |
| Settings | `environment` | Deployment values: the Tavily and Firecrawl keys, the public addresses and signing keys of the PDF and video links, `DB_GATEWAY_INSTANCE`/`DB_GATEWAY_CONNECTION`, `MCP_WORKSPACE_DIR`. "Use the default" removes a saved value. A change is used at once, except what is read only at start (the signing keys, Treasury restart". See `src/environment_settings.py`. |
| Email | `email` (key `smtp`) | The SMTP server, port, connection (`ssl`, `starttls` or `none`), sender, password, standing recipients and allowed domains. Gmail `smtp.gmail.com` 465 ssl; Outlook / Microsoft 365 `smtp.office365.com` 587 starttls; Proton Mail needs Proton Mail Bridge running, then `127.0.0.1` 1025 starttls with the Bridge's own password. Gmail, Outlook, Yahoo and iCloud need an app password. A relay without a login needs none. A send uses the saved values at once. See `src/services/app_config.py`. |
| Limits | `tuning` | Caps and lifetimes of PDF merging and video downloads (below). Used from Armory's next start. See `src/services/capability_tuning.py`. |
| Tool approval | `policy` (key `force_tool_approval`) | One switch: every answer asks a person before each tool runs, whatever the person chose. Off until switched. Armory owns the rule because it holds the tools; Portcullis reads it for each answer (`GET /admin/tool-approval`, `PUT /admin/tool-approval` with `{"value": true|false}`) and requires approval if Armory does not answer. `GET` also says `stored`: false until the switch was saved once. See `src/services/tool_policy.py`. |

## Limits

PDF merging (`pdf_merger`):

| Key | Default | Meaning |
|---|---|---|
| `file_ttl_hours` | 1 | How long an uploaded or merged file is kept. |
| `sweep_interval_minutes` | 10 | How often expired files are removed. |
| `download_link_minutes` | 60 | How long a signed download link works. |
| `mcp_wait_seconds` | 100 | How long a tool call waits for a merge before it answers "still running" (at most 100). |
| `limits.max_file_mb`, `limits.max_session_mb` | 100, 500 | Size caps for one file and for one account's stored files. |
| `limits.max_segments`, `limits.max_output_pages`, `limits.max_image_megapixels` | 50, 2000, 80 | Caps on one merge. |
| `limits.max_concurrent_merges`, `limits.job_timeout_seconds` | 2, 120 | Parallel merges and the time one may take. |

Files are in `.data/armory/pdf_merger/store/`.

Video downloads (`media_downloader`):

| Key | Default | Meaning |
|---|---|---|
| `file_ttl_hours` | 1 | How long a finished download is kept. |
| `sweep_interval_minutes` | 10 | How often expired files are removed. |
| `download_link_minutes` | 60 | How long a signed download link works. |
| `limits.max_file_mb`, `limits.max_duration_minutes`, `limits.max_session_mb` | 500, 120, 2048 | Size and length caps for one file and for one account's stored files. |
| `limits.max_concurrent_downloads`, `limits.max_queued_downloads`, `limits.max_caller_downloads` | 2, 8, 2 | Parallel, waiting and per-account jobs. |
| `limits.job_timeout_minutes` | 30 | A job running longer is stopped. |

Downloads are cache: `.cache/armory/media_downloader/`; logs are in `.data/armory/media_downloader/logs/`.

## What stays in `.env`

Only what you prefer to keep out of the database. Where Armory listens (`host`, `port`) is in the tracked
`configs/config_app.json`. `.env.example` lists them. Never put a real value in a tracked file.

Citadel peer addresses come from Treasury’s service catalog. `treasury_url` in `configs/config_app.json` (overridden by `TREASURY_URL`) is the bootstrap address; `advertise_url` or `CITADEL_ADVERTISE_URL` names Armory’s reachable base address. Pin peers in Treasury Admin, Services.
