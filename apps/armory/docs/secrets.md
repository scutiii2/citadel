# .env

The actual credential values that `../configs/*.json` refers to by name
via `${VAR}` placeholders (e.g. `"password": "${SMTP_PASSWORD}"`), plus
the server's own deployment settings. One file, `mcp_server/.env`,
gitignored; `.env.example` is the committed template with every variable
and its explanation.

- **Server** - `MCP_HOST`, `MCP_PORT`. Not secrets in the "must never
  leak" sense, but deployment-specific and kept with the ones that are.
- **Internal API auth** - Ed25519 identity keys are generated automatically.
  `CITADEL_IDENTITY_DIR` holds the private key; `CITADEL_TRUST_DIR` distributes only public keys.
  Every internal request requires a short-lived service assertion; user calls also carry a signed requester token.
- **SMTP** - `SMTP_PASSWORD`, backing `config_email.json`'s `"password"`.
- **SSH** - `SSH_HOST_KEY_POLICY`, `SSH_KNOWN_HOSTS`. Applies to every SSH
  connection this server makes (`services/ssh.py`). No credentials.

`run.py` loads `.env` before anything else (`utils/env_file.py`). If it is
missing, it is built once: from the old `.secrets/secret_*.env` files when
they exist (values are copied over; the folder is left for you to delete),
otherwise from `.env.example`. A variable already set in the process
environment wins over the file.

In production, prefer having the service manager, container runtime, or
a secrets manager put these variables in the environment directly
instead of a file on disk - nothing else has to change for that to work.
