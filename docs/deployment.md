# Deploying Citadel with Docker

Citadel runs as containers from one `docker-compose.yml`:

| Service | Role | Port |
|---|---|---|
| `ember_web` | user web app, disabled (reference only; the Ember Windows app replaces it) | 26502, unused |
| `portcullis_admin` | admin web app: accounts, roles, invites, settings | 26501 |
| `legion_admin` | admin web app: agents, connections | 26500 |
| `armory_admin` | admin web app: capabilities, connections | 26503 |
| `stronghold_admin` | admin web app: usage, analytics, tickets, usage settings, tool services | 26504 |
| `treasury_admin` | admin web app: Treasury instances, connections and service addresses | 26505 |
| `portcullis` | backend for both web apps | internal |
| `armory` | MCP server (capabilities, including Server Manager) | internal 29600 |
| `legion` | AI agent | internal |
| `treasury` | database gateway | internal 29602 |
| `stronghold` | product logic, called only by portcullis | internal 29650 |

Only the five admin web apps publish ports (on `127.0.0.1`; the ZimaOS overlay opens them to the LAN). The rest talk over the internal `core` network. Laya is not in this stack: it runs
from the separate `LayaModel` project (see "Laya" below) and legion reaches it through the host's published port, `http://host.docker.internal:29220`.

## 1. Local (Windows, macOS, Linux with Docker Desktop or Engine)

1. **The gateways are separate stacks.** ConversationGateway (29407) and DecisionGateway (29406) are not in this compose file. Each runs from its own repo (`AI/ModelProviders/<name>`), with its own `.env` (`SERVICE_ADMIN_PASSWORD`) and its own `docker compose up -d --build`; see "ConversationGateway" and "DecisionGateway" below. Start Citadel first: it creates the `citadel_core` network they join, so Legion still reaches them as `http://conversationgateway:29407` and `http://decisiongateway:29406`.
2. **Create the `.env` files.** Run `python tools/setup_env.py` (the `live` branch carries it too). It makes the root `.env` and each `apps/<app>/.env` from its `.env.example`, fills `BOOTSTRAP_ADMIN_PASSWORD` with a random value, and never overwrites a file that exists or prints a secret. Open the files to read the passwords. The root `.env` is required: every service bind-mounts it.
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
two things for the box: it publishes the five admin web ports (26500, 26501, 26503 to 26505) on all interfaces so the LAN can reach them; each login page is the only protection, so keep the box off the public internet, and it mounts the
Obsidian vault into `armory`. It needs Compose 2.24 or newer (`docker compose version`).

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

   Put `ConversationGateway` and `DecisionGateway` in `/media/ZimaOS-HD/Apps/ModelProviders/` and run each from its own folder (see "ConversationGateway" and "DecisionGateway" below). Citadel needs neither folder.
   Already cloned `main`? Switch in place; the containers keep running:
   `git fetch origin live && git switch -c live --track origin/live`.

2. **Deploy `LayaModel` separately** (it is its own project and Citadel's compose does not start it). Run
   `docker compose up -d --build` in the `LayaModel` folder (`/media/ZimaOS-HD/Apps/ModelServices/DSC_Laya_Model`), in any order relative
   to Citadel. It publishes port 29220 on the host and DecisionGateway reaches it at `http://host.docker.internal:29220`
   (Compose maps that name to the host with `extra_hosts`), so the two stacks share no Docker network. Set
   that address on the `laya` gateway in DecisionGateway (see "DecisionGateway" below); if you change `LAYA_PORT` in `LayaModel`,
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
   | `apps/legion/.env` | `HF_TOKEN` if used. Model provider keys, the Laya token and the TypeSafe key are saved in ConversationGateway and DecisionGateway, not here |
   | `apps/treasury/.env` | Connection secrets such as Postgres DSNs, if a connection saved in Treasury Admin references any |
   | `apps/portcullis/.env` | `BOOTSTRAP_ADMIN_*` (first admin account) |
   | `apps/stronghold/.env` | Nothing is needed |
   | `.env` (root) | `BOOTSTRAP_ADMIN_PASSWORD` and the optional settings in `.env.example` |

   - Compose supplies `CITADEL_SERVICE`, `CITADEL_TRUST_DIR` and `CITADEL_IDENTITY_DIR`. Keep the trust and identity mounts; authentication is mandatory.
   - Compose sets `TREASURY_URL` and `CITADEL_ADVERTISE_URL` for each service; every service registers its own address with Treasury at start, and finds the others in Treasury's catalog (Treasury Admin, Services). A gateway entry that points at a service
     published on the host uses `http://host.docker.internal:<port>` (both gateway containers have that name, so a ConversationGateway entry can reach OmniRoute at `http://host.docker.internal:20128`). Do not use `localhost` or
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

It leaves out other docs, skills, the rest of `tools/`, the Python `tests/` folders and `apps/ember_cli`. `e2e/` and the
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
app runs while `ember_web` is disabled (Plan 8), so this section applies again only when one is back (port 26502); keep the admin apps (26500 to 26505) on the LAN. Public signup must stay off, because anyone with
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

## ConversationGateway

Legion's Anthropic-protocol and OpenAI-protocol agents call their models through ConversationGateway. It is its own stack, deployed from its own repo, and other services may use it too.

- **Source and start**: `AI/ModelProviders/ConversationGateway` (on ZimaOS `/media/ZimaOS-HD/Apps/ModelProviders/ConversationGateway`). Run `docker compose up -d --build` in that folder, after Citadel is up: it joins `citadel_core`, so Legion reaches it as `http://conversationgateway:29407`.
- **Admin password**: `SERVICE_ADMIN_PASSWORD` in that folder's `.env` (copy `.env.example`). It refuses to start without it.
- **First start**: open `http://<host>:29407/admin/`, create an access token for Legion. Then open the Legion admin app (`http://<host>:26500`), go to **Connections**, and save the gateway address (`http://conversationgateway:29407` inside Docker) and that token. They are stored in Treasury, not in a `.env` file. On `/admin/gateways.html` save one gateway per file in `apps/legion/gateways/anthropic/` that your agents use, with the same id as the filename (`claude`, `openrouter`, ...). No restart is needed; agents pick the settings up within half a minute.
- **Outside callers**: the port is published on all interfaces. Give each caller its own token; it connects to `http://<host>:29407` and sends the token as `X-Internal-Token`. There is no TLS in front.
- Provider keys, gateway entries and tokens live in its `conversationgateway_data` volume (project `conversationgateway`). Back it up with the other volumes.

## Stronghold

Portcullis calls Stronghold's product routes. Legion connects to Stronghold's signed `/mcp` endpoint for short- and long-term memory.

- **Storage**: Treasury, connection `stronghold` (`stronghold.db` in `.data/treasury/`). the `stronghold` connection is built in; Stronghold registers its own instance.
- **Keys**: `.data/stronghold/keys.json` is made on first start. It holds the key that encrypts saved calendar links and the web push key pair. Back the folder up. Without the file, saved links must be entered again and browsers must subscribe to push again.
- **Settings**: `docker/configs/stronghold/app.json` (the `calendar` block). The `calendar` block in Portcullis's config and `EMBER_VAPID_*` in its `.env` are no longer read.
- **Notes shared with agents**: Armory's notes tools read Stronghold's database. Compose sets `DB_GATEWAY_INSTANCE=armory` and `DB_GATEWAY_CONNECTION=stronghold` for Armory, as the starting values, and Armory registers instance `armory` with that connection itself. A value saved on the Settings page of Armory Admin wins over them.
- Stronghold reads Legion's agent registry from `.data/legion/` (mounted read-only) and calls Armory for the assistant memory.
- **Token limits and prices**: `usage.six_hour_token_limit`, `usage.weekly_token_limit` and the `pricing` block are in `docker/configs/stronghold/app.json` (Stronghold keeps usage). A limit set in Portcullis's config is ignored.
- Stronghold calls Portcullis's `/internal` routes with signed service assertions (account standing, admin switches, email, Errors log). Its address comes from Treasury’s catalog.

Stronghold keeps long-term memory as plain Markdown on the `.data/stronghold` volume by default (`/data/brain` in the container). Include this folder and its `.originals` subfolders in backups. To move the folder, mount a writable volume, set `STRONGHOLD_BRAIN_ROOT` to its path and restart Stronghold. The live brain settings cap the bytes used by managed files and their revert copies in each account.

### Short-term memory rollout

The built-in Stronghold MCP connection needs no configuration. Restart Legion
to load the connection and deploy Legion and Stronghold from the same repo
version so Legion's `ask` tool accepts the chat ID Stronghold sends.

## Tool services

Before using read aloud, dictation, audio attachments, or document attachments, configure Bard, Scribe, and Reader in **Stronghold Admin → Tool services**. Deploy compatible builds of Stronghold, Portcullis, and Stronghold Admin together.

1. Enter each REST address. On the shared Docker network, use `http://bard:29400`, `http://scribe:29401`, and `http://reader:29402`. Treasury must be reachable to register addresses. Enter a service name when Treasury does not recognize an address.
2. Enter the same per-caller tool tokens used before the move. Add backups in order and supply per-address tokens where needed. Save and use **Test** to check the saved addresses and credentials.
3. Confirm read aloud, live dictation, and attachments. The Portcullis reverse proxy must pass WebSocket upgrades and allow connections to stay open for at least 270 seconds. The Config issues page identifies missing configurations.

Armory's REST façade and Connections page remain until Plan 22. Citadel's speech, dictation, and attachment features use the new Stronghold configuration. Stronghold only streams Bard files whose origin it recorded, so clips created before cutover or through Bard's MCP tool return 404. Legion chooses MCP origins independently. Separate Scribe or Reader backing stores can make files uploaded to a REST backup unavailable to an agent using a different origin.

## DecisionGateway

Legion's decision agents and its automatic routing ask Laya and Jev through DecisionGateway. It is its own stack, deployed from its own repo, and other services may use it too.

- **Source and start**: `AI/ModelProviders/DecisionGateway` (on ZimaOS `/media/ZimaOS-HD/Apps/ModelProviders/DecisionGateway`). Run `docker compose up -d --build` in that folder, after Citadel is up: it joins `citadel_core`, so Legion reaches it as `http://decisiongateway:29406`.
- **Admin password**: `SERVICE_ADMIN_PASSWORD` in that folder's `.env` (copy `.env.example`). It refuses to start without it.
- **First start**: open `http://<host>:29406/admin/`, create an access token for Legion. In the Legion admin app, **Connections**, save the address (`http://decisiongateway:29406` inside Docker) and that token in the DecisionGateway card.
- **Gateways**: on `/admin/gateways.html` save two entries with exactly these ids. `laya`: kind `scuti`, URL of the Laya model service (`http://host.docker.internal:29220`), its token if it has one, and the strategy and window that used to be in `gateways/decision/laya.json` (`english-then-typed`, `4096`). `jev`: kind `typesafe`, model `jev-latest`, and the TypeSafe API key. Legion treats `laya` as the local gateway and `jev` as the cloud one.
- **Outside callers**: port 29406 is published on all interfaces. Give each caller its own token. There is no TLS in front.
- `LAYA_SERVICE_URL`, `LAYA_TOKEN` and `TYPESAFE_API_KEY` in `apps/legion/.env` are no longer read.

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
| A gateway fails with `network citadel_core ... not found` | Start Citadel first; it creates the network. |
| Legion: `ConversationGateway is unreachable` | The gateway is not running, or Legion's saved address is wrong. Run `docker compose up -d` in the gateway's folder and check the Connections page. |
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
