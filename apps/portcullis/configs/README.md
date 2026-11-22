# configs

`config_app.json` - where Portcullis listens, its cookie and Treasury’s bootstrap address, tracked, with no
`.example` twin. Nothing secret is kept here: secrets and private values are in `../.env` (see `../.env.example`).
Restart Portcullis after editing; the Config issues page checks the file.

**The policy settings are not here.** Session length, the role of a new account, email verification, the login rate
limit, the IP filter, security headers, device fingerprinting and database backups are set in Portcullis Admin >
Workspace settings and kept in `.data/portcullis/settings.db` (table `app_config`, see `src/services/app_policy.py`).
A saved value wins over the built-in default shown below; Portcullis reads them when it starts, so a change is used
from the next start. The rows marked *(Admin)* are those settings.

**Pricing and token limits are not Portcullis's.** Stronghold owns the model price table and the usage limits
(Stronghold Admin > Usage settings). Portcullis asks Stronghold for the prices (`GET /usage/pricing`,
refreshed at most once a minute) to price the chat messages it reads from its own database.

| Key | Meaning |
|---|---|
| `host`, `port` | Where uvicorn listens. `EMBER_API_HOST` / `EMBER_API_PORT` override them. |
| `database_path` | Optional. SQLite file, relative to the portcullis folder; default `.data/portcullis/ember_api.db` in the Citadel folder. |
| `session_cookie_name` | Name of the login cookie. |
| `session_hours` *(Admin)* | How long a login lasts. |
| `cookie_secure` | `true` once served over HTTPS (the cookie is then never sent over plain HTTP). |
| `default_role` *(Admin)* | Role every newly registered account gets (created with `chat.use` + `tools.use` if missing). |
| `require_email_verification` *(Admin)* | `true` (default): an account holds no permissions until its email is verified. `false`: unverified accounts work, registration sends no code, and `/api/auth/me` reports `email_verification_required: false`. |
| `agents_registry_path` | ai_agent's `.data/agent_registry.json` (relative to the portcullis folder). portcullis only proxies to agents listed there. |
| `agents_registry_url` | Optional. ai_agent's `GET /registry`, e.g. `http://10.0.0.5:29603/registry`, for an ai_agent in another directory or on another machine. Wins over `agents_registry_path`; authenticated with a short-lived Portcullis service assertion for Legion. Fetched with a 3 s timeout and cached 5 s; if it stops answering, the last good list is used for 60 s, then there are no agents. Leave it out for a same-machine setup. |
| `treasury_url` | Treasury bootstrap base address; `TREASURY_URL` overrides it. |
| `advertise_url` | Optional reachable Portcullis base address; `CITADEL_ADVERTISE_URL` overrides it. |
| `security` | Optional block; only `trusted_proxies` is read from the file, the rest is *(Admin)*. |
| `security.trusted_proxies` | Peers allowed to name the real client in `X-Forwarded-For` (last hop only). Default loopback, for Vite's proxy. |
| `security.rate_limit` *(Admin)* | `enabled`, `scope` (`ip` / `account` / `both`), `max_attempts` failed logins within `window_seconds` -> login refused (`429` + `Retry-After`) until `lockout_seconds` after the last failure. |
| `security.ip_filter` *(Admin)* | `allow_list` / `deny_list` of addresses or CIDRs, checked on every request except `/api/outside/*` for the allow list (`403`). Deny wins; a non-empty allow list refuses everything else. |
| `security.outside_ip_filter` *(Admin)* | `allow_list` / `deny_list` for `/api/outside/*` only (`403`). The main `allow_list` does not apply there (it is for people); the main `deny_list` still does. Enabling outside clients therefore opens a door that a LAN-only main allow list does not close; use this list (and each client's `ip_allow`) to limit it. |
| `security.headers` *(Admin)* | `enabled` adds nosniff, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a locked-down CSP to every response; `hsts_max_age` > 0 adds HSTS (HTTPS only). |
| `security.fingerprint` *(Admin)* | `enabled`: a login from a device the account never used (a hash of the `signals`: `user_agent`, `accept_language`, `ip_subnet` = /24 or /64 network) is written to the activity log - never blocked. Users see and forget their devices on the Account page. |
| `backup` *(Admin)* | Optional block: `enabled` (default true), `every_hours` (24) and `keep` (14). portcullis copies its database to `backups/<name>-<UTC time>.db` beside the database at startup (unless the newest copy is younger than `every_hours`) and then every `every_hours`, keeping the newest `keep`. Uses SQLite's online backup, so it is safe while running, and checks each copy. A failure is written to the Errors log. `python -m scripts.backup_db` makes one now. |

Peer addresses resolve through Treasury’s catalog for each request. Pin an address in Treasury Admin, Services.
