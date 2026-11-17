# Deploying Citadel with Docker

Citadel runs as containers from one `docker-compose.yml`:

| Service | Role | Port |
|---|---|---|
| `ember_web` | user web app, disabled (reference only; the Ember Windows app replaces it) | 26502, unused |
| `portcullis_admin` | admin web app: accounts, roles, invites, settings | 26501 |
| `legion_admin` | admin web app: agents, connections | 26500 |
| `armory_admin` | admin web app: capabilities, extensions | 26503 |
| `stronghold_admin` | admin web app: usage, analytics, tickets, tuning | 26504 |
| `treasury_admin` | admin web app: Treasury instances (read-only) | 26505 |
| `portcullis` | backend for both web apps | internal |
| `armory` | MCP server (capabilities, including Server Manager) | internal 29600 |
| `legion` | AI agent | internal |
| `treasury` | database gateway | internal 29602 |
| `stronghold` | product logic, called only by portcullis | internal 29650 |
| `conversationgateway` | chat-model gateway for Legion, shared with callers outside Citadel | 29407 on all interfaces |

Only the two web apps publish ports. The rest talk over the internal `core` network. Laya is not in this stack: it runs
from the separate `LayaModel` project (see "Laya" below) and legion reaches it through the host's published port, `http://host.docker.internal:29220`.

## 1. Local (Windows, macOS, Linux with Docker Desktop or Engine)

1. Service identity keys are made on first start; no shared token or auth setting is needed. Each service writes only its own public trust folder and private `identity_*` volume; peers mount that public folder read-only. Backing up private identity volumes is optional: a lost key is remade and peers reload its new public key.
   Per-app secrets live in `apps/<app>/.env` and are loaded when the file exists.
2. Start the stack:

   ```bash
   docker compose up -d --build
   ```

3. Open http://localhost:26501 (portcullis_admin; the other admin apps are on 26500 and 26503 to 26505). All bind to `127.0.0.1`.

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
two things for the box: it publishes the two web ports on all interfaces so the LAN can reach them, and it mounts the
Obsidian vault into `armory`. It needs Compose 2.24 or newer (`docker compose version`).

Without the overlay the UIs stay on `127.0.0.1` and are not reachable from the LAN. Deployment sets
`COMPOSE_FILE=docker-compose.yml:docker-compose.zima.yml` in the server's root `.env`, so a plain
`docker compose up -d --build` uses both files.

### Deploy from the PC: `tools\deploy.bat`

Double-click it for a menu:

| Option | Does |
|---|---|
| 1 | Publish code to the `live` branch (see "The live branch") |
| 2 | Copy the gitignored `.env` and `config_*.json` files to the server as one `tar` stream over a single `ssh` connection (one password prompt), and set `COMPOSE_FILE` in the server's `.env` |
| 3 | Both: publish, then push |
| 4, 5 | Dry-run previews of 1 and 2 |
| 6 | Chown helper: copies `chown -R <user> <dir>` to the clipboard and opens the server's web terminal (root shell) so you can paste it |

The target is `lex@scutiserver1.local:/media/ZimaOS-HD/Apps/Citadel`. The server refuses root over ssh, so the script logs
in as `lex`; the web terminal is at `http://scutiserver1.local:7681/`. If option 2 fails with `Permission denied`, run
option 6 once (it also offers itself after a failed push). Set `DEPLOY_HOST`, `DEPLOY_DIR` and `DEPLOY_WEB_PORT` before
running to change them. After each action the script prints the commands to run on the server. Option 2 overwrites the
server's copies, including `EMBER_SECRETS_KEY`, so do not push over secrets the server generated itself.

### First-time setup on the box

1. **Clone the `live` branch** onto the data disk, not the system partition. Publish it first (option 1). A private
   repo needs a deploy key or token.

   ```bash
   mkdir -p /media/ZimaOS-HD/Apps
   git clone -b live <your-repo-url> /media/ZimaOS-HD/Apps/Citadel
   ```

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

   No root `.env` is needed: the internal token is made on first start.

   Per-app files: copy each committed `.env.example` and fill in the values.

   ```bash
   cp apps/armory/.env.example apps/armory/.env
   cp apps/legion/.env.example apps/legion/.env
   cp apps/treasury/.env.example apps/treasury/.env
   cp apps/portcullis/.env.example apps/portcullis/.env
   chmod 600 .env apps/*/.env apps/portcullis/.env
   ```

   | File | Keys to fill in |
   |---|---|
   | `apps/armory/.env` | Only the capability keys you use: `SMTP_PASSWORD`, `TAVILY_API_KEY`, `FIRECRAWL_API_KEY`, `LAYA_URL` (`http://legion:29611/mcp` to group tickets with the triage agent) |
   | `apps/legion/.env` | `HF_TOKEN` if used. Model provider keys, the Laya token and the TypeSafe key are saved in ConversationGateway and DecisionGateway, not here |
   | `apps/treasury/.env` | Connection secrets such as Postgres DSNs, if `config_connections.json` references any |
   | `apps/portcullis/.env` | `BOOTSTRAP_ADMIN_*` (first admin account), `SMTP_*`, `MAIL_FROM_ADDRESS` |

   - Compose supplies `CITADEL_SERVICE`, `CITADEL_TRUST_DIR` and `CITADEL_IDENTITY_DIR`. Keep the trust and identity mounts; authentication is mandatory.
   - Skip `MCP_HOST`, `MCP_PORT` and service URLs such as `DB_GATEWAY_URL`; Compose sets them. A gateway entry that points at a service
     published on the host uses `http://host.docker.internal:<port>`. Do not use `localhost` or
     the server's hostname for another service.
   - **Laya settings** (`LAYA_TOKEN`, `LAYA_REPLICAS`, `LAYA_PORT`) belong in `LayaModel`'s own `.env`, not here. Each
     replica loads its own copy of the models in RAM, so keep `LAYA_REPLICAS` low on a small box.
   - `apps/portcullis/.env` must exist before the first start. Compose bind-mounts it, and if it is missing Docker
     creates a directory in its place and portcullis fails. portcullis writes `EMBER_SECRETS_KEY` into it, so keep it
     when you rebuild.

4. **Create the config files git does not hold.** `config_*.json` is gitignored (deploy option 2 copies yours). Compose
   mounts the tracked files under `docker/configs/` over `config_extensions.json`, `config_servers.json`,
   `config_app.json` and `config_connections.json`. For the rest:

   | File | On a fresh clone |
   |---|---|
   | `apps/legion/configs/config_tuning.json` | Created from its `.example` automatically |
   | `apps/portcullis/configs/config_pricing.json` | Created from its `.example` automatically |
   | `apps/armory/configs/config_email.json`, `config_tickets.json` | Copy each `.example` and fill in `config_email.json` |

   These files are baked into the image at build time, so a change made to them inside the container is lost when
   armory is rebuilt. Edit the file instead.

   `docker/configs/armory/extensions.json` and `docker/configs/armory/capabilities.json` are the exception: they are
   mounted writable, so extensions added on the Extensions page and capability toggles set on the Capabilities page of
   armory_admin are saved into those files and survive restarts and rebuilds. On the device they differ from git after
   the first change; keep them when you update (`git stash` or `git update-index --skip-worktree`).

5. **Start:**

   ```bash
   docker compose up -d --build
   ```

6. Open `http://<zima-ip>:26502` and `http://<zima-ip>:26501` from any device on your network.

### Updating

Publish and push from the PC (`tools\deploy.bat`, option 3), then on the box:

```bash
cd /media/ZimaOS-HD/Apps/Citadel
git pull
docker compose up -d --build
```

Use `up -d`, not `docker restart`, after any `.env` edit: `restart` does not reload `env_file`. If only `.env` or config
changed and no code did, add `--force-recreate`.

### The live branch

The box needs only what the stack builds from, not the whole repo. `tools/publish_live.py` builds a `live` branch from
`main` with just these paths:

- `docker-compose.yml`, `docker-compose.zima.yml`, `.env.example`, `docker/`
- `apps/armory`, `apps/legion`, `apps/treasury`, `apps/stronghold`, `apps/portcullis`, `apps/portcullis_admin`, `apps/legion_admin`, `apps/armory_admin`, `apps/stronghold_admin`, `apps/treasury_admin`
- `docs/deployment.md`

It leaves out other docs, skills, `tools/`, the Python `tests/` folders and `apps/ember_cli`. `e2e/` and the
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

## ConversationGateway

Legion's Anthropic-protocol and OpenAI-protocol agents call their models through ConversationGateway. It is a service of this stack, built from its own repo, and other services may use it too.

- **Source**: `AI/ModelProviders/ConversationGateway` beside this workspace. On a server set `CONVERSATION_GATEWAY_DIR` in the root `.env` to where that repo sits.
- **Admin password**: `CONVERSATION_GATEWAY_ADMIN_PASSWORD` in the root `.env`. The stack refuses to start without it.
- **First start**: open `http://<host>:29407/admin/`, create an access token for Legion. Then open the Legion admin app (`http://<host>:26500`), go to **Connections**, and save the gateway address (`http://conversationgateway:29407` inside Docker) and that token. They are stored in Treasury, not in a `.env` file. On `/admin/gateways.html` save one gateway per file in `apps/legion/gateways/anthropic/` that your agents use, with the same id as the filename (`claude`, `openrouter`, ...). No restart is needed; agents pick the settings up within half a minute.
- **Outside callers**: the port is published on all interfaces. Give each caller its own token; it connects to `http://<host>:29407` and sends the token as `X-Internal-Token`. There is no TLS in front.
- **One copy per host**: do not also start the gateway's own `docker-compose.yml` on the same host; port 29407 would clash.
- Provider keys, gateway entries and tokens live in the `conversationgateway_data` volume. Back it up with the other volumes.

## Stronghold

Product logic, called only by Portcullis. The calendar is the first feature that lives there.

- **Storage**: Treasury, connection `stronghold` (`stronghold.db` in `.data/treasury/`). `docker/configs/treasury/connections.json` must list the `stronghold` connection and instance.
- **Keys**: `.data/stronghold/keys.json` is made on first start. It holds the key that encrypts saved calendar links and the web push key pair. Back the folder up. Without the file, saved links must be entered again and browsers must subscribe to push again.
- **Settings**: `docker/configs/stronghold/app.json` (the `calendar` block). The `calendar` block in Portcullis's config and `EMBER_VAPID_*` in its `.env` are no longer read.
- **Notes shared with agents**: Armory's notes tools read Stronghold's database. Compose sets `DB_GATEWAY_INSTANCE=armory` and `DB_GATEWAY_CONNECTION=stronghold` for Armory, and `docker/configs/treasury/connections.json` lists `stronghold` under instance `armory`. A value for these in `apps/armory/.env` is overridden by Compose.
- Stronghold reads Legion's agent registry from `.data/legion/` (mounted read-only) and calls Armory for the assistant memory.
- **Token limits and prices**: `usage.six_hour_token_limit`, `usage.weekly_token_limit` and the `pricing` block are in `docker/configs/stronghold/app.json` (Stronghold keeps usage). A limit set in Portcullis's config is ignored.
- Stronghold calls Portcullis's `/internal` routes with the shared internal token (account standing, admin switches, email, Errors log). Nothing to configure: Compose sets `PORTCULLIS_URL`.

## DecisionGateway

Legion's decision agents and its automatic routing ask Laya and Jev through DecisionGateway. It is a service of this stack, built from its own repo, and other services may use it too.

- **Source**: `AI/ModelProviders/DecisionGateway` beside this workspace. On a server set `DECISION_GATEWAY_DIR` in the root `.env` to where that repo sits.
- **Admin password**: `DECISION_GATEWAY_ADMIN_PASSWORD` in the root `.env`. The stack refuses to start without it.
- **First start**: open `http://<host>:29406/admin/`, create an access token for Legion. In the Legion admin app, **Connections**, save the address (`http://decisiongateway:29406` inside Docker) and that token in the DecisionGateway card.
- **Gateways**: on `/admin/gateways.html` save two entries with exactly these ids. `laya`: kind `scuti`, URL of the Laya model service (`http://host.docker.internal:29220`), its token if it has one, and the strategy and window that used to be in `gateways/decision/laya.json` (`english-then-typed`, `4096`). `jev`: kind `typesafe`, model `jev-latest`, and the TypeSafe API key. Legion treats `laya` as the local gateway and `jev` as the cloud one.
- **Outside callers**: port 29406 is published on all interfaces. Give each caller its own token. There is no TLS in front.
- **One copy per host**: do not also start the gateway's own `docker-compose.yml` on the same host.
- `LAYA_SERVICE_URL`, `LAYA_TOKEN` and `TYPESAFE_API_KEY` in `apps/legion/.env` are no longer read.

## 3. Server Manager

The Server Manager capability (chat id `server`) lists, starts, stops and restarts Docker containers and reads their
logs. It works through the host Docker socket, which `docker-compose.yml` mounts into `armory`
(`/var/run/docker.sock`).

Enable it on the Capabilities page of armory_admin, or in `docker/configs/armory/capabilities.json`:

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

| Symptom | Cause and fix |
|---|---|
| `401` or `403` between backends | Check service identity/trust mounts, clock synchronization and the caller's route policy. There is no legacy token fallback. |
| legion cannot reach Laya | LayaModel is not running, or its published port is not 29220. Run `docker compose ps` in `LayaModel`, then `docker compose exec legion python -c "import urllib.request as u; print(u.urlopen('http://host.docker.internal:29220/health').status)"`. Expect 200. |
| `.env` files seem to be missing | They are hidden dotfiles. Run `ls -la apps/armory`. |
| `scp` will not log in | Check `DEPLOY_HOST` and that the folder exists. Run `ssh <host>` by hand to test. |
| `openssl: command not found` | Use the `/dev/urandom` command in first-time setup, step 3. A failed `echo` leaves an empty `.env`, so run it again. |
| portcullis fails and `apps/portcullis/.env` is a directory | Compose created it because the file was missing. Run `rmdir apps/portcullis/.env`, then `touch apps/portcullis/.env`, then start again. |
| UI loads on the box but not on another device | Overlay not used. Check `COMPOSE_FILE` in the root `.env`, or add `-f docker-compose.zima.yml`. |
| Overlay still binds `127.0.0.1` | Compose older than 2.24 ignores `!override`. Update Compose, or edit the `ports` lines in the main file. |
| Port already in use | Another app uses 26502 or 26501. Change the left side of the port mapping. |
| `permission denied` on the Docker socket | The container cannot read `/var/run/docker.sock`. Check its owner and mode on the host. |
| Capability toggle reverted after a rebuild | `docker/configs/armory/capabilities.json` was reset (for example by `git checkout` or `git stash`) or is not mounted. Check `docker-compose.yml` mounts it, then set the toggle again. |
| Funnel page loads but big files stall or time out | Check `docker inspect tailscale --format "{{.RestartCount}}"`. The ZimaOS Tailscale app's entrypoint (`tailscaled ... & sleep 10; tailscale web --listen 0.0.0.0:5252`) can exit after 10 s and restart the container in a loop. Append `; wait` to that entrypoint line in `/var/lib/casaos/apps/tailscale/docker-compose.yml` and run `docker compose up -d` there. A CasaOS app update may overwrite it. |

## Runtime data and cache

Every service keeps its runtime data in `.data/<service>/` and files it can make again in `.cache/<service>/`, both in the Citadel folder (gitignored). Compose bind-mounts them into the containers; running a service directly uses the same folders. Set `CITADEL_DATA_DIR` and `CITADEL_CACHE_DIR` in the root `.env` to move them (a relative value is relative to the Citadel folder). Back up `.data/`; `.cache/` can be deleted. Service keys stay in the `identity_*` and `trust_*` Docker volumes, not in `.data/`.

## Overriding a service's `.env` from the root `.env`

A value in the root `.env` wins over the same name in `apps/<service>/.env`. Empty values are ignored.
- `TAVILY_API_KEY=...` applies to every service that lists that name in its `.env.example` or `.env`.
- `ARMORY__TAVILY_API_KEY=...` applies to Armory only (prefixes `ARMORY__`, `LEGION__`, `PORTCULLIS__`, `STRONGHOLD__`, `TREASURY__`; two underscores). It wins over the plain form.

Other root variables, such as the gateway admin passwords and `CITADEL_DATA_DIR`, never reach a service's settings. Compose mounts the whole root `.env` read-only at `/citadel.env` in each service, so a process that can read files there can read those passwords too.
