# configs

`config_app.json` is tracked; there is no `.example` twin. It holds where Stronghold listens and its Treasury bootstrap address:

| Key | Meaning |
|---|---|
| `host` | Address to bind. `127.0.0.1` keeps Stronghold on this machine. |
| `port` | Port to listen on. |

`STRONGHOLD_HOST` and `STRONGHOLD_PORT` win over the file; Compose sets them. Restart Stronghold after editing.

The usage limits and the price table are not here. An administrator sets them on the Usage settings page of Stronghold
Admin and they are kept in `.data/stronghold/settings.db` (table `limits_and_prices`); a change is used at once.
Stronghold is the only owner of both: Portcullis keeps no copy and reads the prices from `GET /usage/pricing` to price
the chat messages it holds. The tool service tokens are on the Tool services page, not in `.env`.

Stronghold's data and keys are in `.data/stronghold/` in the Citadel folder.

Optional `treasury_url` defaults to `http://127.0.0.1:29602`; `TREASURY_URL` overrides it. Optional `advertise_url` names this service’s reachable base address; `CITADEL_ADVERTISE_URL` overrides it. Other Citadel addresses come from Treasury’s service catalog, with pins on Treasury Admin, Services.
