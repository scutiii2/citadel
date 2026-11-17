# configs

`config_app.json` is tracked; there is no `.example` twin. It holds where Armory listens and its Treasury bootstrap address:

| Key | Meaning |
|---|---|
| `host` | Address to bind. `127.0.0.1` keeps Armory on this machine. Use `0.0.0.0` only behind something that authenticates (Docker Compose does, through `MCP_HOST`). |
| `port` | Port to listen on. |

`MCP_HOST` and `MCP_PORT` win over the file; Compose sets them. Restart Armory after editing.

Everything else an administrator changes is in Armory Admin and saved in `.data/armory/settings.db`: see
[`../docs/settings.md`](../docs/settings.md).

Optional `treasury_url` defaults to `http://127.0.0.1:29602`; `TREASURY_URL` overrides it. Optional `advertise_url` names this service’s reachable base address; `CITADEL_ADVERTISE_URL` overrides it. Other Citadel addresses come from Treasury’s service catalog, with pins on Treasury Admin, Services.
