# src/configs/

Structured, per-deployment settings: the mail settings and the two capability tuning files. Loaded by
`services/app_config.py` (see that module's docstring for the full loader
mechanics); the mail path comes from `Settings.email_config_path` in `config.py`.

- **`config_email.json`** - SMTP settings and the standing
  recipient list.
  `smtp_server`/
  `smtp_port`/`security` depend on which provider `from` lives on -
  since JSON has no comments, the tracked file only shows Gmail;
  the other two mainstream cases:

  ```jsonc
  // Outlook / Hotmail / Live / Microsoft 365
  {
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "security": "starttls",
    "from": "you@outlook.com",
    "password": "${SMTP_PASSWORD}"
  }

  // Proton Mail - needs Proton Mail Bridge running locally first;
  // Proton doesn't expose SMTP directly even with an app password.
  // smtp_server/smtp_port come from the Bridge's own settings pane,
  // and the password is the Bridge-generated one, not the mailbox
  // password.
  {
    "smtp_server": "127.0.0.1",
    "smtp_port": 1025,
    "security": "starttls",
    "from": "you@proton.me",
    "password": "${SMTP_PASSWORD}"
  }
  ```

  All three still need an app-specific password per this file's
  `email.py` docstring - Gmail and Outlook because of 2FA, Proton
  because Bridge issues its own.
- **`config_media_downloader.json`** - caps and lifetimes of the media downloader.
  Its path can be changed with `MCP_MEDIA_CONFIG_PATH`. Restart Armory after editing.

  | Key | Meaning |
  |---|---|
  | `file_ttl_hours` | How long a finished download is kept. |
  | `sweep_interval_minutes` | How often expired files are removed. |
  | `download_link_minutes` | How long a signed download link works. |
  | `limits.max_file_mb`, `limits.max_duration_minutes`, `limits.max_session_mb` | Size and length caps for one file and for one account's stored files. |
  | `limits.max_concurrent_downloads`, `limits.max_queued_downloads`, `limits.max_caller_downloads` | Parallel, waiting and per-account jobs. |
  | `limits.job_timeout_minutes` | A job running longer is stopped. |

  The signing key and public address are in `.env` (`MCP_MEDIA_SIGNING_KEY`, `MCP_MEDIA_PUBLIC_BASE_URL`).
  Downloads are cache: `.cache/armory/media_downloader/` in the Citadel folder; logs are in `.data/armory/media_downloader/logs/`.
- **`config_pdf_merger.json`** - caps and lifetimes of the PDF merger.
  Its path can be changed with `MCP_PDF_MERGER_CONFIG_PATH`. Restart Armory after editing.

  | Key | Meaning |
  |---|---|
  | `file_ttl_hours` | How long an uploaded or merged file is kept. |
  | `sweep_interval_minutes` | How often expired files are removed. |
  | `download_link_minutes` | How long a signed download link works. |
  | `mcp_wait_seconds` | How long a tool call waits for a merge before it answers "still running". |
  | `limits.max_file_mb`, `limits.max_session_mb` | Size caps for one file and for one account's stored files. |
  | `limits.max_segments`, `limits.max_output_pages`, `limits.max_image_megapixels` | Caps on one merge. |
  | `limits.max_concurrent_merges`, `limits.job_timeout_seconds` | Parallel merges and the time one may take. |

  The signing key and public address are in `.env` (`PDF_MERGER_SIGNING_KEY`, `MCP_PDF_MERGER_PUBLIC_BASE_URL`).
  Files are in `.data/armory/pdf_merger/store/` in the Citadel folder.
- **Run-time settings are not here.** Extensions, capability toggles and ticket
  settings (tags, hourly cap, elevation, Laya limits) are changed from admin
  pages, so they live in `.data/armory/settings.db` in the Citadel folder (tables
  `extensions`, `capabilities`, `settings`). See `services/settings_store.py`.
  - **Capabilities** start off. A new install loads none of them; an administrator turns each one on, on the
    deployed machine, from the Capabilities page. A capability with no entry is never loaded.
  - **Extensions** are added on the Extensions page: name, URL and, for a tool service (Bard, Scribe, Reader,
    Lens, Mimic), the token its own admin page made for Armory (Tokens card). Armory keeps the token in
    `settings.db` and sends it in the `X-Internal-Token` header, the header those services read their
    per-caller token from. The page never shows the token again. Tick "Runs in this stack" for a server of this
    stack: it signs a service assertion instead of using a token.
  - **Ticket settings** have no file. The defaults are in
    `capabilities/tickets/utils/config.py`; staff change them with
    `GET`/`PATCH /ticket-admin/settings` (see `capabilities/tickets/routes.py`).
    Changes apply to the next ticket, no restart.

Each file's top-level JSON *is* its content - there's no wrapper key.
Anything sensitive is a `${VAR}` placeholder resolved from
`../.env` at load time, never a literal value in these files -
see `services/app_config.py`'s docstring for the substitution syntax.
Every JSON file here is tracked, and none has an `.example` twin. Values that must
stay out of git are `${VAR}` placeholders (`${SMTP_FROM}`, `${SMTP_PASSWORD}`),
filled from `../.env`; `../.env.example` lists them.
