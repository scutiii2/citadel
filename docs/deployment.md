# Deploying Citadel with Docker

Citadel runs as six containers from one `docker-compose.yml`:

| Service | Role | Port |
|---|---|---|
| `ember_web` | user web app | 5173 |
| `ember_admin` | admin web app | 5176 |
| `ember_api` | backend for both web apps | internal |
| `armory` | MCP server (capabilities, including Server Manager) | internal 8010 |
| `garrison` | AI agent | internal |
| `treasury` | database gateway | internal 8071 |

Only the two web apps publish ports. The rest talk over the internal `core` network.

## 1. Local (Windows, macOS, Linux with Docker Desktop or Engine)

1. Copy `.env.example` to `.env` in the repo root and set `INTERNAL_API_TOKEN` to a long random string.
   Compose refuses to start without it.
2. Per-app secrets live in `apps/<app>/.env`. They are loaded when the file exists.
3. Start the stack:

   ```bash
   docker compose up -d --build
   ```

4. Open http://localhost:5173 (ember_web) and http://localhost:5176 (ember_admin).
   Both bind to `127.0.0.1`, so only this machine can reach them.

Rebuild one service after a code change:

```bash
docker compose up -d --build armory
```

Other useful commands:

```bash
docker compose ps              # state of every service
docker compose logs -f armory  # follow one service's logs
docker compose down            # stop and remove containers (volumes are kept)
```

Anything you edit inside a running container is lost on rebuild. Keep changes in the repo.

## 2. ZimaOS

ZimaOS is Linux with Docker and Compose, so the same compose file works. The overlay `docker-compose.zima.yml`
publishes the two web ports on all interfaces so the LAN can reach them.

1. Check the Compose version. The overlay needs 2.24 or newer:

   ```bash
   docker compose version
   ```

2. Publish the `live` branch from your PC (see "The live branch" below), then clone it onto the data disk, not the
   system partition. Later updates are a `git pull`, with no manual copying.

   ```bash
   mkdir -p /media/ZimaOS-HD/Apps
   git clone -b live <your-repo-url> /media/ZimaOS-HD/Apps/Citadel
   cd /media/ZimaOS-HD/Apps/Citadel
   ```

   Already cloned `main`? Switch that clone in place. The containers keep running:

   ```bash
   git fetch origin live
   git switch -c live --track origin/live
   ```

   A private repo needs a deploy key or token. Run every later command from this folder.
3. Create the `.env` files. They are gitignored, so `live` does not hold them, and a `git pull` never touches them.
   Names that start with a dot are hidden: use `ls -la` to see them.

   Root `.env` (required, Compose refuses to start without it). ZimaOS has no `openssl`, so build the token from
   `/dev/urandom`:

   ```bash
   echo "INTERNAL_API_TOKEN=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" > .env
   cat .env                      # INTERNAL_API_TOKEN= then 64 hex characters
   ```

   The root token reaches every service and overrides any `INTERNAL_API_TOKEN` in a per-app file, so leave that line
   out of those.

   Per-app `.env` files. Each app has a committed `.env.example`; copy it and fill in the values:

   ```bash
   cp apps/armory/.env.example apps/armory/.env
   cp apps/garrison/.env.example apps/garrison/.env
   cp apps/treasury/.env.example apps/treasury/.env
   cp apps/Ember/ember_api/.env.example apps/Ember/ember_api/.env
   ```

   | File | Keys to fill in |
   |---|---|
   | `apps/armory/.env` | Only the capability keys you use: `SMTP_PASSWORD`, `TEAMS_WEBHOOK_URL`, `TAVILY_API_KEY`, `FIRECRAWL_API_KEY`, `LAYA_URL` |
   | `apps/garrison/.env` | `CLAUDE_API_KEY`, or the keys of the gateway your agents use; `HF_TOKEN` if used |
   | `apps/treasury/.env` | Connection secrets such as Postgres DSNs, if `config_connections.json` references any |
   | `apps/Ember/ember_api/.env` | `BOOTSTRAP_ADMIN_*` (first admin account), `SMTP_*`, `MAIL_FROM_ADDRESS` |

   Skip `MCP_HOST`, `MCP_PORT` and service URLs such as `DB_GATEWAY_URL`; Compose sets them. Do not use `localhost`
   for another service.

   **Laya.** The Laya models run in the `laya` service (replicas) behind `laya_lb`, built from the sibling project
   `Python/LayaAgent` (outside this repo, so it must exist next to `Citadel/`). Compose sets
   `LAYA_SERVICE_URL=http://laya_lb:9120` for Garrison. Set `LAYA_REPLICAS` (default 2), `LAYA_PORT` and `LAYA_TOKEN`
   in the root `.env`; if `LAYA_TOKEN` is set, put the same value in `apps/garrison/.env`. Each replica loads its own
   copy of the models, and `laya_lb` starts only after a replica is healthy (first start downloads the weights, so allow
   a few minutes). Do not run LayaAgent's own `docker-compose.yml` at the same time: it uses the same port.

   `apps/Ember/ember_api/.env` must exist before the first start. Compose bind-mounts it, and if it is missing Docker
   creates a directory in its place and ember_api fails. ember_api writes `EMBER_SECRETS_KEY` into this file, so keep
   it when you rebuild.

   Lock the files down:

   ```bash
   chmod 600 .env apps/armory/.env apps/garrison/.env apps/treasury/.env apps/Ember/ember_api/.env
   ```

   **Or copy them from your PC.** This keeps your existing values, including `EMBER_SECRETS_KEY`, and replaces the
   root token with the PC's, so use the same token on both machines if they talk to each other. From the repo root on
   the PC (PowerShell):

   ```bash
   tar -cf $env:TEMP\envs.tar .env apps/armory/.env apps/garrison/.env apps/treasury/.env apps/Ember/ember_api/.env
   scp $env:TEMP\envs.tar myuser@<zima-ip>:/tmp/envs.tar
   del $env:TEMP\envs.tar
   ```

   Then on the box as `root`:

   ```bash
   tar -xf /tmp/envs.tar -C /media/ZimaOS-HD/Apps/Citadel
   rm /tmp/envs.tar
   ```

   Use a real username and IP, not the placeholders. If `root` cannot log in over SSH, send to the other account's
   `/tmp` and unpack as `root`, as above. The archive holds secrets, so delete it afterwards. The result overwrites
   any `.env` already on the box.
4. Create the config files that git does not hold. `config_*.json` is gitignored. Compose mounts the files under
   `docker/configs/` (tracked) over `config_extensions.json`, `config_servers.json`, `config_app.json` and
   `config_connections.json`. These stay inside the containers:

   | File | On a fresh clone |
   |---|---|
   | `apps/garrison/configs/config_tuning.json` | Created from its `.example` automatically |
   | `apps/Ember/ember_api/configs/config_pricing.json` | Created from its `.example` automatically |
   | `apps/armory/configs/config_capabilities.json` | Not confirmed; copy the `.example` to be safe |
   | `apps/armory/configs/config_email.json` | May fail without it; copy the `.example` and fill it in |
   | `apps/armory/configs/config_tickets.json` | May fail without it; copy the `.example` |

   ```bash
   cd apps/armory/configs
   cp config_capabilities.json.example config_capabilities.json
   cp config_email.json.example config_email.json
   cp config_tickets.json.example config_tickets.json
   cd ../../..
   ```

   These files are baked into the image at build time, so a change made in the Capabilities page of ember_admin is
   lost when armory is rebuilt.
4. Start with the overlay:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.zima.yml up -d --build
   ```

5. Open `http://<zima-ip>:5173` and `http://<zima-ip>:5176` from any device on your network.

Without the overlay the UIs stay on `127.0.0.1` and are not reachable from the LAN.

### Dashboard tiles

Containers started from the CLI may not show in the ZimaOS dashboard (v1.8.0). The "import Docker CLI" option in
Custom Install does not fit: it creates a new container from one `docker run` command instead of adopting the
compose containers, and it cannot build our images. Add external links instead. The containers stay under compose.

1. In the dashboard, click **+** and choose **Add external link**. The label may differ by version.
2. Add two links, using the box's LAN IP (not `localhost`) so they work from other devices:

   | Name | URL | Icon |
   |---|---|---|
   | Ember | `http://<zima-ip>:5173` | `apps/Ember/ember_web/public/icons/icon-512.png` |
   | Ember Admin | `http://<zima-ip>:5176` | `apps/Ember/ember_admin/public/icons/icon-512.png` |

3. If the dashboard asks for an image URL, use the running app: `http://<zima-ip>:5173/icons/icon-512.png` and
   `http://<zima-ip>:5176/icons/icon-512.png`. Avoid `icon-maskable-512.png`; its padding makes the tile look small.

Give the box a fixed IP (a DHCP reservation in the router) so the links keep working. If your version has no external
link option, use a browser bookmark.

To update later, publish from the PC, then on the box:

```bash
cd /media/ZimaOS-HD/Apps/Citadel
git pull
docker compose -f docker-compose.yml -f docker-compose.zima.yml up -d --build
```

Use `up -d`, not `docker restart`, after any `.env` edit: `restart` does not reload `env_file`.

`config_*.json` files are gitignored, so a capability toggle such as `server` in
`apps/armory/configs/config_capabilities.json` does not arrive with `git pull`. Set it on the box.

### The live branch

The box needs only what the stack builds from, not the whole repo. `tools/publish_live.py` builds a `live` branch
from `main` with just those paths:

- `docker-compose.yml`, `docker-compose.zima.yml`, `.env.example`, `docker/`
- `apps/armory`, `apps/garrison`, `apps/treasury`, `apps/Ember`
- `docs/deployment.md`

It leaves out other docs, skills, `tools/`, the Python `tests/` folders and `apps/Ember/ember_cli`.
`e2e/` and the `src/*.test.ts` files stay because the web apps' tsconfig includes them. The path lists are at the top
of the script; add a path there when you add a compose service.

From the repo root on the PC:

```bash
py tools\publish_live.py --dry-run     # show what would be published
py tools\publish_live.py               # create or update origin/live
```

or double-click `tools\publish_live.bat`. The script reads committed `main` without touching your working tree,
index or branch, so commit `main` first. The `live` commit is built on top of the remote tip, so pushes are normal
fast-forwards with no force-push. A run with no changes prints "already up to date".

The old `apps/armory/zima_host.yaml` is from before the stack was split into containers. Do not use it.

## 3. Server Manager

The Server Manager capability (chat id `server`) lists, starts, stops and restarts Docker containers and reads their
logs. It works through the host Docker socket, which `docker-compose.yml` mounts into `armory`:

```yaml
- /var/run/docker.sock:/var/run/docker.sock
```

Enable it in `apps/armory/configs/config_capabilities.json`:

```json
"server": { "enabled": true }
```

You can also toggle it on the Capabilities page in ember_admin. A toggle made there lives in the container and is lost
when armory is rebuilt, so set the repo file to keep it.

Tools: `tool_srv_listApps`, `tool_srv_startApp`, `tool_srv_stopApp`, `tool_srv_restartApp`, `tool_srv_readAppLogs`,
`tool_srv_getAppLogs`. Starting or restarting an app also starts a watcher that emails the person who started it when
the app crashes or logs errors. See `apps/armory/src/capabilities/server_manager/README.md`.

### Security

- The Docker socket is root on the host. Anyone who can call the `tool_srv_*` tools can control every container.
- Server Manager lists every container on the host, not only Citadel's. On ZimaOS that includes your other apps.
- Keep `INTERNAL_API_TOKEN` secret. Do not publish armory's port 8010.
- Keep `server` disabled where you do not need it.

### Checking it works

After the stack is up and `server` is enabled, ask the assistant to list apps, or call `tool_srv_listApps`. It should
return all six `citadel-*` containers as `running`.

If it reports `Could not reach Docker from this process`, the socket mount is missing. Recreate armory:

```bash
docker compose up -d armory
```

## 4. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `set INTERNAL_API_TOKEN in .env` | The root `.env` is missing or empty. |
| `.env` files seem to be missing | They are hidden dotfiles. Run `ls -la apps/armory`. |
| `scp` will not log in | Use a real user and IP, not `user@<zima-ip>`. If `root` is not allowed, send to the other account's `/tmp` and unpack as `root`. |
| `openssl: command not found` | Use the `/dev/urandom` command in section 2, step 3. A failed `echo` leaves an empty `.env`, so run it again. |
| ember_api fails and `apps/Ember/ember_api/.env` is a directory | Compose created it because the file was missing. Run `rmdir apps/Ember/ember_api/.env`, then `touch apps/Ember/ember_api/.env`, then start again. |
| UI loads on the PC but not on another device | Overlay not used. Add `-f docker-compose.zima.yml`. |
| Overlay still binds `127.0.0.1` | Compose older than 2.24 ignores `!override`. Update Compose, or edit the `ports` lines in the main file. |
| Port already in use | Another app uses 5173 or 5176. Change the left side of the port mapping. |
| `permission denied` on the Docker socket | The container cannot read `/var/run/docker.sock`. Check its owner and mode on the host. |
| Capability toggle reverted after a rebuild | It was changed inside the container. Edit `config_capabilities.json` in the repo. |
