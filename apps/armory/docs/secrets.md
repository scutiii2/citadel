# .env

The server's own deployment settings and the credential values you
prefer to keep out of the database. One file, `mcp_server/.env`,
gitignored; `.env.example` is the committed template with every variable
and its explanation.

- **Server** - `MCP_HOST`, `MCP_PORT`. Not secrets in the "must never
  leak" sense, but deployment-specific and kept with the ones that are.
- **Internal API auth** - Ed25519 identity keys are generated automatically.
  `CITADEL_IDENTITY_DIR` holds the private key; `CITADEL_TRUST_DIR` distributes only public keys.
  Every internal request requires a short-lived service assertion; user calls also carry a signed requester token.
- **Email** - not here. The SMTP server, sender and password are set on the Email page of Armory Admin and kept in
  `settings.db`.

`run.py` loads `.env` before anything else (`utils/env_file.py`). If it is
missing, it is built once: from the old `.secrets/secret_*.env` files when
they exist (values are copied over; the folder is left for you to delete),
otherwise from `.env.example`. A variable already set in the process
environment wins over the file.

In production, prefer having the service manager, container runtime, or
a secrets manager put these variables in the environment directly
instead of a file on disk - nothing else has to change for that to work.
