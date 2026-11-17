# configs

`config_app.json` is tracked; there is no `.example` twin. It holds only where Armory listens:

| Key | Meaning |
|---|---|
| `host` | Address to bind. `127.0.0.1` keeps Armory on this machine. Use `0.0.0.0` only behind something that authenticates (Docker Compose does, through `MCP_HOST`). |
| `port` | Port to listen on. |

`MCP_HOST` and `MCP_PORT` win over the file; Compose sets them. Restart Armory after editing.

Everything else an administrator changes is in Armory Admin and saved in `.data/armory/settings.db`: see
[`../docs/settings.md`](../docs/settings.md).
