# Deploying Citadel with Docker

Citadel runs as containers from one `docker-compose.yml`:

| Service | Role | Port |
|---|---|---|
| `portcullis_admin` | admin web app: accounts, roles, invites, settings | 26501 |
| `legion_admin` | admin web app: agents, connections | 26500 |
| `armory_admin` | admin web app: capabilities, connections | 26503 |
| `stronghold_admin` | admin web app: usage, analytics, tickets, usage settings, tool services | 26504 |
| `treasury_admin` | admin web app: Treasury instances, connections and service addresses | 26505 |
| `portcullis` | backend for both web apps | internal |
| `armory` | MCP server (capabilities, including Server Manager) | internal 29600 |
| `legion` | AI agent, with the chat and decision model gateways built in | internal |
| `treasury` | database gateway | internal 29602 |
| `stronghold` | product logic, called only by portcullis | internal 29650 |

Only the five admin web apps publish ports (on `127.0.0.1`; the ZimaOS overlay opens them to the LAN). The rest talk over the internal `core` network; Legion also joins `llm_net` to reach model providers. Laya is not in this stack: it runs
from the separate `LayaModel` project (see "Laya" below) and legion reaches it through the host's published port, `http://host.docker.internal:29220`.

## 1. Local (Windows, macOS, Linux with Docker Desktop or Engine)

1. **The model gateways are built into Legion.** There are no gateway containers, ports, tokens or admin passwords. Gateway entries, with their keys, are added on the Legion admin app, **Connections**, **Model gateways**, and kept in Legion's database. See "Model gateways" below.
2. **Create the `.env` files.** Run `python tools/setup_env.py` (the `live` branch carries it too). It makes the root `.env`, an empty `.env.gateways` and each `apps/<app>/.env` from its `.env.example`, fills `BOOTSTRAP_ADMIN_PASSWORD` and the two gateway admin passwords with random values, and never overwrites a file that exists or prints a secret. Open the files to read the passwords. The root `.env` is required: every service bind-mounts it.
   Service identity keys are made on first start; no shared token or auth setting is needed. Each service writes only its own public trust folder and private `identity_*` volume; peers mount that public folder read-only. Backing up private identity volumes is optional: a lost key is remade and peers reload its new public key.
3. Start the stack:

   ```bash
   docker compose up -d --build
   ```

4. Open http://localhost:26501 (portcullis_admin; the other admin apps are on 26500 and 26503 to 26505). All bind to `127.0.0.1`.

To rebuild one service, run `docker compose up -d --build <service>`, or double-click the `dev_deploy.bat` in that
service's folder (`apps/armory`, `apps/legion`, `apps/treasury`, `apps/stronghold`, `apps/portcullis`, `portcullis_admin`, `legion_admin`, `armory_admin`, `stronghold_admin`, `treasury_admin`).

```bash
docker compose ps              # state of every service
docker compose logs -f armory  # follow one service's logs
docker compose down            # stop and remove containers (volumes are kept)
```

Anything you edit inside a running container is lost on rebuild. Keep changes in the repo.

## 2. ZimaOS

ZimaOS is Linux with Docker and Compose, so the same compose file works. The overlay `docker-compose.zima.yml` does
one thing for the box: it publishes the five admin web ports (26500, 26501, 26503 to 26505) on all interfaces so the LAN can reach them; each login page is the only protection, so keep the box off the public internet. It needs Compose 2.24 or newer (`docker compose version`).

Without the overlay the UIs stay on `127.0.0.1` and are not reachable from the LAN. Deployment sets
`COMPOSE_FILE=docker-compose.yml:docker-compose.zima.yml` in the server's root `.env`, so a plain
`docker compose up -d --build` uses both files.

### Deploy from the PC: `tools\deploy.bat`

Double-click it for a menu:

| Option | Does |
|---|---|
| 1 | Publish code to the `live` branch (see "The live branch") |
| 2 | Copy the gitignored `.env` files to the server (configs come with git) as one `tar` stream over a single `ssh` connection (one password prompt), and set `COMPOSE_FILE` in the server's `.env` |
| 3 | Both: publish, then push |
| 4, 5 | Dry-run previews of 1 and 2 |
| 6 | Chown helper: copies `chown -R <user> <dir>` to the clipboard and opens the server's web terminal (root shell) so you can paste it |

The target is `lex@scutiserver1.local:/media/ZimaOS-HD/Apps/Applications/Citadel`. The server refuses root over ssh, so the script logs
in as `lex`; the web terminal is at `http://scutiserver1.local:7681/`. If option 2 fails with `Permission denied`, run
option 6 once (it also offers itself after a failed push). Set `DEPLOY_HOST`, `DEPLOY_DIR` and `DEPLOY_WEB_PORT` before
running to change them. After each action the script prints the commands to run on the server. Option 2 overwrites the
server's copies, including `EMBER_SECRETS_KEY`, so do not push over secrets the server generated itself.

### First-time setup on the box

1. **Clone the `live` branch** onto the data disk, not the system partition. Publish it first (option 1). A private
   repo needs a deploy key or token.

   ```bash
   mkdir -p /media/ZimaOS-HD/Apps/Applications /media/ZimaOS-HD/Apps/ModelProviders
   git clone -b live <your-repo-url> /media/ZimaOS-HD/Apps/Applications/Citadel
   ```

   Already cloned `main`? Switch in place; the containers keep running:
   `git fetch origin live && git switch -c live --track origin/live`.

2. **Deploy `LayaModel` separately** (it is its own project and Citadel's compose does not start it). Run
   `docker compose up -d --build` in the `LayaModel` folder (`/media/ZimaOS-HD/Apps/ModelServices/DSC_Laya_Model`), in any order relative
   to Citadel. It publishes port 29220 on the host and Legion's decision gateway reaches it at `http://host.docker.internal:29220`
   (Compose maps that name to the host with `extra_hosts`), so the two stacks share no Docker network. Set
   that address on the `laya` entry under Model gateways (see below); if you change `LAYA_PORT` in `LayaModel`,
   change the port there to match. A container cannot resolve the server's own hostname (`scutiserver1`). See
   `LayaModel/deployment.md` for replicas, port and weights.

3. **Create the `.env` files.** They are gitignored, so `live` does not hold them and `git pull` never touches them.
   The simplest way is deploy option 2, which copies yours from the PC. To create them by hand, run from the Citadel
   folder (names that start with a dot are hidden: use `ls -la`).

   The root `.env` is required (see "Local" step 2). Run `python tools/setup_env.py` to make it and every per-app file from the committed `.env.example` files with random passwords; or copy them by hand:

   ```bash
   cp .env.example .env
   for app in armory legion treasury stronghold portcullis; do cp apps/$app/.env.example apps/$app/.env; done
   chmod 600 .env apps/*/.env
   ```

   Then set `BOOTSTRAP_ADMIN_PASSWORD` yourself if you copied by hand.

   | File | Keys to fill in |
   |---|---|
   | `apps/armory/.env` | Nothing is needed. Set the capability keys you use (Tavily, Firecrawl), `LAYA_URL` (`http://legion:29611/mcp` to group tickets with the triage agent) and the email account in Armory Admin (Settings and Email pages) |
   | `apps/legion/.env` | `HF_TOKEN` if used. Model provider keys are saved with the gateway entries in Legion's database, not here |
   | `apps/treasury/.env` | Connection secrets such as Postgres DSNs, if a connection saved in Treasury Admin references any |
   | `apps/portcullis/.env` | `BOOTSTRAP_ADMIN_*` (first admin account) |
   | `apps/stronghold/.env` | Nothing is needed |
   | `.env` (root) | `BOOTSTRAP_ADMIN_PASSWORD` and the optional settings in `.env.example` |

   - Compose supplies `CITADEL_SERVICE`, `CITADEL_TRUST_DIR` and `CITADEL_IDENTITY_DIR`. Keep the trust and identity mounts; authentication is mandatory.
   - Compose sets `TREASURY_URL` and `CITADEL_ADVERTISE_URL` for each service; every service registers its own address with Treasury at start, and finds the others in Treasury's catalog (Treasury Admin, Services). A gateway entry that points at a service
     published on the host uses `http://host.docker.internal:<port>` (Legion has that name, so a chat gateway entry can reach OmniRoute at `http://host.docker.internal:20128`). Do not use `localhost` or
     the server's hostname for another service.
   - **Laya settings** (`LAYA_TOKEN`, `LAYA_REPLICAS`, `LAYA_PORT`) belong in `LayaModel`'s own `.env`, not here. Each
     replica loads its own copy of the models in RAM, so keep `LAYA_REPLICAS` low on a small box.
   - `apps/portcullis/.env` must exist before the first start. Compose bind-mounts it, and if it is missing Docker
     creates a directory in its place and portcullis fails. portcullis writes `EMBER_SECRETS_KEY` into it, so keep it
     when you rebuild.

4. **Configs are tracked.** Every `configs/*.json` is in git and none has an `.example` twin; each `configs/` folder has a
   `README.md` describing its keys (Armory’s listener and Treasury bootstrap are in `configs/config_app.json`; other settings are in Armory Admin). Secrets are `${NAME}` placeholders filled from the `.env` files (see the
   `.env.example` beside each). Compose mounts the tracked files under `docker/configs/` read-only for container values (Portcullis's, Stronghold's
   and Treasury's `config_app.json`). Everything an
   admin changes at run time is saved in `.data/<service>/`, so it survives rebuilds and never shows in git: Armory's
   connections, capability toggles and ticket settings and Legion's servers (each in `settings.db`), Legion's tuning and
   prompts, and the instances Treasury's callers register. A new install starts with every Armory capability off, no
   Armory extension; Legion defaults its main server to Armory’s catalog address. An administrator turns on and adds what the machine needs. Stronghold alone
   owns the usage limits and the price table; Portcullis reads the prices from it.
   Set up email on the Email page of Armory Admin before using it.

5. **Start:**

   ```bash
   docker compose up -d --build
   ```

6. Open `http://<zima-ip>:26501` (and the other admin apps, 26500 and 26503 to 26505) from any device on your network.

### Updating

Publish and push from the PC (`tools\deploy.bat`, option 3), then on the box:

```bash
cd /media/ZimaOS-HD/Apps/Applications/Citadel
git pull
docker compose up -d --build
```

Use `up -d`, not `docker restart`, after any `.env` edit: `restart` does not reload `env_file`. If only `.env` or config
changed and no code did, add `--force-recreate`.

### The live branch

The box needs only what the stack builds from, not the whole repo. `tools/publish_live.py` builds a `live` branch from
`main` with just these paths:

- `docker-compose.yml`, `docker-compose.zima.yml`, `.env.example`, `docker/`, `tools/setup_env.py`
- `apps/armory`, `apps/legion`, `apps/treasury`, `apps/stronghold`, `apps/portcullis`, `apps/portcullis_admin`, `apps/legion_admin`, `apps/armory_admin`, `apps/stronghold_admin`, `apps/treasury_admin`
- `docs/deployment.md`

It leaves out other docs, skills, the rest of `tools/` and the Python `tests/` folders. `e2e/` and the
`src/*.test.ts` files stay because the web apps' tsconfig includes them. The path lists are at the top of the script;
add a path there when you add a compose service.

Commit `main` first: the script reads committed `main` without touching your working tree, index or branch. The `live`
commit is built on top of the remote tip, so pushes are normal fast-forwards with no force-push. A run with no changes
prints "already up to date". To run it without the menu: `py tools\publish_live.py [--dry-run]`.

### Releasing

A plain publish (`tools\deploy.bat` option 1) only updates the `live` branch, so it is fine for test deploys. A release is a separate step: set `VERSION` (and `pyproject.toml` where it has a version, to the same number), commit, then run `tools\deploy.bat` option R or `py tools\publish_live.py --release`. That publishes to `live` and tags the `main` commit `vX.Y.Z` and the live commit `live-vX.Y.Z`. A version already released with different live files is refused, so bump `VERSION`. While a version is not officially released yet, add `--replace` to move its tags.

`tools\make_zip.bat` then builds `zip_versions\Citadel-<VERSION>.zip` (no `tools/`, no git-ignored files, no older ZIPs; `.env.example` is included) and opens GitHub's new-release page for the tag.

### Dashboard tiles

Containers started from the CLI may not show in the ZimaOS dashboard (v1.8.0), and the "import Docker CLI" option in
Custom Install cannot adopt compose containers or build our images. Add external links instead; the containers stay
under compose.

1. In the dashboard, click **+** and choose **Add external link**. The label may differ by version.
2. Add a link per admin app, using the box's LAN IP (not `localhost`) so they work from other devices:

   | Name | URL | Icon |
   |---|---|---|
   | Ember Admin | `http://<zima-ip>:26501` | `apps/portcullis_admin/public/icons/icon-512.png` |

3. If the dashboard asks for an image URL, use `http://<zima-ip>:26501/icons/icon-512.png`. Avoid `icon-maskable-512.png`; its padding makes the tile look small.

Give the box a fixed IP (a DHCP reservation in the router) so the links keep working. If your version has no external
link option, use a browser bookmark.

### Public access with Tailscale Funnel

Funnel publishes a web app on `https://<box>.<tailnet>.ts.net/` without a Tailscale client on the viewing device. No user web
app runs and there is no browser app, so this section applies again only when one is back (port 26502); keep the admin apps (26500 to 26505) on the LAN. Public signup must stay off, because anyone with
the URL can reach the login page.

1. In the Tailscale admin console, give the box the `funnel` attribute (`nodeAttrs` in the access controls) and turn on
   MagicDNS and HTTPS. The first `funnel` command prints an approval link if something is missing.
2. Set `"security": {"rate_limit": {"scope": "account"}}` in the portcullis config (`docker/configs/portcullis/app.json`).
   Behind Funnel every client reaches nginx through the Docker bridge, so the IP-based lockout would count all users as
   one address. With the default `"both"`, five wrong passwords from anyone would lock everyone out.
3. Rebuild and start Funnel. The `docker exec tailscale` prefix is for the ZimaOS Tailscale app; drop it if Tailscale
   runs on the host:

   ```bash
   docker compose up -d --build portcullis
   docker exec tailscale tailscale funnel --bg 26502
   docker exec tailscale tailscale funnel status
   ```

   Turn it off with `docker exec tailscale tailscale funnel --https=443 off`.

Funnel sends `X-Forwarded-Proto: https` for TLS requests. nginx passes it on, and portcullis adds `Secure` to the session
cookie when the request came through a `trusted_proxies` peer with that header. Plain-HTTP LAN access at
`http://<zima-ip>:26502` keeps working, with no `Secure` flag, so leave `cookie_secure` at `false`.

## Showing the admin apps inside ServiceHub

The five admin apps refuse to be framed (`frame-ancestors 'none'`). To let ServiceHub show them in its frame, set `HUB_FRAME_ANCESTORS` in the root `.env` to the exact origins you open the hub with (space-separated, quoted), for example `HUB_FRAME_ANCESTORS="http://scutiserver1.local:29880 http://192.168.1.50:29880"`, then run `docker compose up -d` to recreate the admin containers. Only those pages may frame them. In ServiceHub register each admin with "Open directly" ticked (the proxy would break their absolute `/assets` and `/api` paths), URL `http://host.docker.internal:26501` (the hub probes it from its container) and Link address `http://scutiserver1.local:26501` (what your browser frames). Unset or empty keeps `'none'`.

## Model gateways

Legion's agents call their models through two gateways that run inside Legion: a chat gateway (Anthropic, OpenAI-compatible and model-service providers) and a decision gateway (Laya, Jev, Ollama). They have no container, host port, access token or admin password, and they are not registered in ServiceHub.

- **Keys and tokens**: paste them into the entry's key or token field on the page. They are saved in Legion's settings database (`.data/legion/settings.db`), write-only (the page shows only that one is saved), and no `.env` file is needed. Optionally a field can hold `env:NAME` to read a variable from `.env.gateways` instead.
- **Entries**: open the Legion admin app (`http://<host>:26500`), **Connections**, **Model gateways**. Add a gateway under *Chat models* or *Decision models*, start from a preset if one fits, then press its Test icon. Entries need no restart; agents pick them up within a minute.
- **Decision entries**: save two with exactly these ids. `laya`: kind `scuti`, URL of the Laya model service (`http://host.docker.internal:29220`), its token if it has one, strategy `english-then-typed`, window `4096`. `jev`: kind `typesafe`, model `jev-latest`, API key `env:TYPESAFE_API_KEY`. Legion treats `laya` as the local gateway and `jev` as the cloud one.
- **Reaching the host**: an entry for a service published on the host (OmniRoute, Ollama, vLLM, Laya) uses `host.docker.internal`, never `127.0.0.1`. Legion's container maps that name to the host.
- **Data**: entries are rows in the `conversation_gateways` and `decision_gateways` tables of `.data/legion/settings.db`. Entries of the older gateway containers are not imported: add them again on the page (the old `gateways.json` files list what they were). The old access tokens are no longer used.
- **Standalone copies**: `AI/ModelProviders/ConversationGateway` and `DecisionGateway` stay as separate projects for other callers. Legion's copy is part of `apps/legion/src/gateway` and is not kept in sync.
- `LAYA_SERVICE_URL`, `LAYA_TOKEN` and `TYPESAFE_API_KEY` in `apps/legion/.env` are not read.


## Stronghold

Portcullis calls Stronghold's product routes. Legion connects to Stronghold's signed `/mcp` endpoint for short-term memory, long-term memory, and skills.

- **Storage**: Treasury, connection `stronghold` (`stronghold.db` in `.data/treasury/`). the `stronghold` connection is built in; Stronghold registers its own instance.
- **Keys**: `.data/stronghold/keys.json` is made on first start. It holds the key that encrypts saved calendar links and the web push key pair. Back the folder up. Without the file, saved links must be entered again and browsers must subscribe to push again.
- **Settings**: `docker/configs/stronghold/app.json` (the `calendar` block). The `calendar` block in Portcullis's config and `EMBER_VAPID_*` in its `.env` are no longer read.
- **Armory's Treasury registration**: Compose sets `DB_GATEWAY_INSTANCE=armory` and `DB_GATEWAY_CONNECTION=stronghold` for Armory, as the starting values, and Armory registers instance `armory` with that connection itself. Armory no longer has notes tools (Plan 22). A value saved on the Settings page of Armory Admin wins over them.
- Stronghold reads Legion's agent registry from `.data/legion/` (mounted read-only).
- **Token limits and prices**: `usage.six_hour_token_limit`, `usage.weekly_token_limit` and the `pricing` block are in `docker/configs/stronghold/app.json` (Stronghold keeps usage). A limit set in Portcullis's config is ignored.
- Stronghold calls Portcullis's `/internal` routes with signed service assertions (account standing, admin switches, email, Errors log). Its address comes from Treasury’s catalog.

Stronghold keeps long-term memory as plain Markdown on the `.data/stronghold` volume by default (`/data/brain` in the container). Include this folder and its `.originals` subfolders in backups. To move the folder, mount a writable volume, set `STRONGHOLD_BRAIN_ROOT` to its path and restart Stronghold. The live brain settings cap the bytes used by managed files and their revert copies in each account.

### Short-term memory rollout

The built-in Stronghold MCP connection needs no configuration. Restart Legion
to load the connection and deploy Legion and Stronghold from the same repo
version so Legion's `ask` tool accepts the chat ID Stronghold sends.

### Skills and recall rollout

Deploy Stronghold and Legion from the same repo version. Ember needs the `stronghold__tool_brain_*`, `stronghold__tool_skill_*` and `stronghold__tool_stack_*` allow globs. If the machine's `agent_overrides.json` replaces `ember.json`, apply the same allow list and notes instructions to the override.

Armory no longer has a `skills` capability (Plan 22). Stronghold stores new skill files in `.skills/` inside each account's Brain folder, so include that folder in backups. Citadel no longer reads or purges the old Armory skill data. Agents can propose those skills again, and Plan 20f will support recreating them by hand.

### Global brain rollout

Deploy Portcullis and Stronghold together so Stronghold can resolve share recipients through Portcullis's signed internal username endpoint. Give `brain.global.write` to roles responsible for editing global content and reviewing shares. Startup grants it to the Administrator role.

Include `<brain root>/_global/` in the same backups as `<brain root>/accounts/`. Both belong on the brain volume. Include Treasury data in backups to preserve share and block records.

## Tool services

Before using read aloud, dictation, audio attachments, or document attachments, configure Bard, Scribe, and Reader in **Stronghold Admin → Tool services**. Deploy compatible builds of Stronghold, Portcullis, and Stronghold Admin together.

1. Enter each REST address. On the shared Docker network, use `http://bard:29400`, `http://scribe:29401`, and `http://reader:29402`. Treasury must be reachable to register addresses. Enter a service name when Treasury does not recognize an address.
2. Enter the same per-caller tool tokens used before the move. Add backups in order and supply per-address tokens where needed. Save and use **Test** to check the saved addresses and credentials.
3. Confirm read aloud, live dictation, and attachments. The Portcullis reverse proxy must pass WebSocket upgrades and allow connections to stay open for at least 270 seconds. The Config issues page identifies missing configurations.

Armory's REST façade and dictation relay are gone (Plan 22). Its Connections page remains because extensions are still stored as connection records there. Citadel's speech, dictation, and attachment features use the new Stronghold configuration. Stronghold only streams Bard files whose origin it recorded, so clips created before cutover or through Bard's MCP tool return 404. Legion chooses MCP origins independently. Separate Scribe or Reader backing stores can make files uploaded to a REST backup unavailable to an agent using a different origin.

## 3. Server Manager

The Server Manager capability (chat id `server`) lists, starts, stops and restarts Docker containers and reads their
logs. It works through the host Docker socket, which `docker-compose.yml` mounts into `armory`
(`/var/run/docker.sock`).

Enable it on the Capabilities page of armory_admin, :

```json
"server": { "enabled": true }
```

You can also toggle it on the Capabilities page in armory_admin, but that toggle lives in the container and is lost when
armory is rebuilt, so set the repo file to keep it. The file is gitignored: set it on the box, or push it with deploy
option 2.

Tools: `tool_srv_listApps`, `tool_srv_startApp`, `tool_srv_stopApp`, `tool_srv_restartApp`, `tool_srv_readAppLogs`,
`tool_srv_getAppLogs`. Starting or restarting an app also starts a watcher that emails the person who started it when
the app crashes or logs errors. See `apps/armory/src/capabilities/server_manager/README.md`.

**Security**

- The Docker socket is root on the host. Anyone who can call the `tool_srv_*` tools can control every container.
- Server Manager lists every container on the host, not only Citadel's. On ZimaOS that includes your other apps.
- Keep each service's private `identity_*` volume private. Do not publish armory's port 29600.
- Keep `server` disabled where you do not need it.

**Checking it works.** With the stack up and `server` enabled, ask the assistant to list apps, or call
`tool_srv_listApps`. It should return the `citadel-*` containers as `running`. If it reports
`Could not reach Docker from this process`, the socket mount is missing; recreate armory with
`docker compose up -d armory`.

## 4. Troubleshooting

A service reports 'connection refused' to a peer: open Treasury Admin, Services; pin the address if the peer registered a wrong one.

| Symptom | Cause and fix |
|---|---|
| `401` or `403` between backends | Check service identity/trust mounts, clock synchronization and the caller's route policy. There is no legacy token fallback. |
| legion cannot reach Laya | LayaModel is not running, or its published port is not 29220. Run `docker compose ps` in `LayaModel`, then `docker compose exec legion python -c "import urllib.request as u; print(u.urlopen('http://host.docker.internal:29220/health').status)"`. Expect 200. |
| `.env` files seem to be missing | They are hidden dotfiles. Run `ls -la apps/armory`. |
| `scp` will not log in | Check `DEPLOY_HOST` and that the folder exists. Run `ssh <host>` by hand to test. |
| Legion: `no gateway is saved` or a gateway named in an agent is missing | Add it under Connections, Model gateways, with the same name the agent uses, and press Test. |
| A model gateway Test says the key was refused | The key is wrong (or an `env:NAME` is not set in `.env.gateways`). Paste it again on the entry and test. |
| A service fails and its `.env` (or the root `.env`) is a directory | Compose created it because the file was missing. Remove the directory, run `python tools/setup_env.py`, then start again. |
| UI loads on the box but not on another device | Overlay not used. Check `COMPOSE_FILE` in the root `.env`, or add `-f docker-compose.zima.yml`. |
| Overlay still binds `127.0.0.1` | Compose older than 2.24 ignores `!override`. Update Compose, or edit the `ports` lines in the main file. |
| Port already in use | Another app uses 26502 or 26501. Change the left side of the port mapping. |
| `permission denied` on the Docker socket | The container cannot read `/var/run/docker.sock`. Check its owner and mode on the host. |
| Capability toggle reverted after a rebuild | `.data/armory/settings.db` was deleted or is not mounted, so every capability started off. Check `docker-compose.yml` mounts `.data/armory`, then turn the capability on again. |
| Funnel page loads but big files stall or time out | Check `docker inspect tailscale --format "{{.RestartCount}}"`. The ZimaOS Tailscale app's entrypoint (`tailscaled ... & sleep 10; tailscale web --listen 0.0.0.0:5252`) can exit after 10 s and restart the container in a loop. Append `; wait` to that entrypoint line in `/var/lib/casaos/apps/tailscale/docker-compose.yml` and run `docker compose up -d` there. A CasaOS app update may overwrite it. |

## Runtime data and cache

Every service keeps its runtime data in `.data/<service>/` and files it can make again in `.cache/<service>/`, both in the Citadel folder (gitignored). Compose bind-mounts them into the containers; running a service directly uses the same folders. Set `CITADEL_DATA_DIR` and `CITADEL_CACHE_DIR` in the root `.env` to move them (a relative value is relative to the Citadel folder). Back up `.data/`; `.cache/` can be deleted. Service keys stay in the `identity_*` and `trust_*` Docker volumes, not in `.data/`.

## Overriding a service's `.env` from the root `.env`

A value in the root `.env` wins over the same name in `apps/<service>/.env`. Empty values are ignored.
- `BOOTSTRAP_ADMIN_PASSWORD=...` applies to every service that lists that name in its `.env.example` or `.env`.
- `PORTCULLIS__BOOTSTRAP_ADMIN_PASSWORD=...` applies to Portcullis only (prefixes `ARMORY__`, `LEGION__`, `PORTCULLIS__`, `STRONGHOLD__`, `TREASURY__`; two underscores). It wins over the plain form.

Other root variables, such as `CITADEL_DATA_DIR`, never reach a service's settings. Compose mounts the whole root `.env` read-only at `/citadel.env` in each service, so a process that can read files there can read those passwords too.

## Security

The model gateways run inside Legion and publish no port. Their keys are rows in Legion's database; the optional `.env.gateways` is loaded by Legion only. The root `.env` is mounted into every service, which is why keys are not kept there. Run `uv run --project libs/citadel_auth python scripts/check_compose.py` from the Citadel root to check these rules.

## Liveness, readiness, and tool failures

`GET /health` is public and answers `{"status":"ok"}` while the process runs.
`GET /ready` requires a signed Citadel service assertion. Authorized calls return
HTTP 200 with dependency addresses and states (`configured`, `reachable`,
`unreachable`, `not_configured`) even during an outage.

| Code | Failure | Retryable |
|---|---|---|
| 1000 | `TOOL_INTERNAL` | No |
| 1001 | `DEP_NOT_CONFIGURED` | No |
| 1002 | `DEP_UNAVAILABLE` | Yes |
| 1003 | `DEP_TIMEOUT` | Yes |
| 1004 | `DEP_AUTH_REJECTED` | No |
| 1005 | `DEP_ERROR` | Maybe |

Citadel services start independently of their peers. Compose uses `depends_on` lists as start-order hints. Readiness reports are diagnostic and guarded actions continue to fail closed. Portcullis exposes an aggregate at `GET /api/admin/ready` for `settings.manage`; the admin screen is pending. Treasury discovers missing addresses through known Compose names and public health checks. Only Legion can reach the two gateways on `llm_net`.
