# Deploying Citadel with Docker

Citadel runs as containers from one `docker-compose.yml`:

| Service | Role | Port |
|---|---|---|
| `ember_web` | user web app | 5173 |
| `ember_admin` | admin web app | 5176 |
| `ember_api` | backend for both web apps | internal |
| `armory` | MCP server (capabilities, including Server Manager) | internal 8010 |
| `garrison` | AI agent | internal |
| `treasury` | database gateway | internal 8071 |
| `laya` (replicas), `laya_lb` | Laya models behind an nginx balancer, built from the sibling `LayaAgent` project | internal 9120 |

Only the two web apps publish ports (`laya_lb` also binds `127.0.0.1:9120`). The rest talk over the internal `core`
network.

## 1. Local (Windows, macOS, Linux with Docker Desktop or Engine)

1. Copy `.env.example` to `.env` in the repo root and set `INTERNAL_API_TOKEN` to a long random string. Compose
   refuses to start without it. Per-app secrets live in `apps/<app>/.env` and are loaded when the file exists.
2. Start the stack:

   ```bash
   docker compose up -d --build
   ```

3. Open http://localhost:5173 (ember_web) and http://localhost:5176 (ember_admin). Both bind to `127.0.0.1`.

To rebuild one service, run `docker compose up -d --build <service>`, or double-click the `dev_deploy.bat` in that
service's folder (`apps/armory`, `apps/garrison`, `apps/treasury`, `apps/Ember/ember_api`, `ember_web`, `ember_admin`).

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
| 2 | Copy the gitignored `.env` and `config_*.json` files to the server over `scp`, and set `COMPOSE_FILE` in the server's `.env` |
| 3 | Both: publish, then push |
| 4, 5 | Dry-run previews of 1 and 2 |

The target is `root@scutiserver1.local:/media/ZimaOS-HD/Apps/Citadel`. Set `DEPLOY_HOST` and `DEPLOY_DIR` before running
to change it. After each action the script prints the commands to run on the server. Option 2 overwrites the server's
copies, including `EMBER_SECRETS_KEY`, so do not push over secrets the server generated itself.

### First-time setup on the box

1. **Clone the `live` branch** onto the data disk, not the system partition. Publish it first (option 1). A private
   repo needs a deploy key or token.

   ```bash
   mkdir -p /media/ZimaOS-HD/Apps
   git clone -b live <your-repo-url> /media/ZimaOS-HD/Apps/Citadel
   ```

   Already cloned `main`? Switch in place; the containers keep running:
   `git fetch origin live && git switch -c live --track origin/live`.

2. **Put `LayaAgent` next to `Citadel`**, at `/media/ZimaOS-HD/Apps/LayaAgent`. It is a separate project, so `live` does
   not carry it. The `laya` service builds from `../LayaAgent`, and `laya_lb` mounts `../LayaAgent/nginx.conf`. Compose
   stops with `path ".../LayaAgent" not found` if it is missing.

3. **Create the `.env` files.** They are gitignored, so `live` does not hold them and `git pull` never touches them.
   The simplest way is deploy option 2, which copies yours from the PC. To create them by hand, run from the Citadel
   folder (names that start with a dot are hidden: use `ls -la`).

   Root `.env` (required). ZimaOS has no `openssl`, so build the token from `/dev/urandom`:

   ```bash
   echo "INTERNAL_API_TOKEN=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" > .env
   ```

   Per-app files: copy each committed `.env.example` and fill in the values.

   ```bash
   cp apps/armory/.env.example apps/armory/.env
   cp apps/garrison/.env.example apps/garrison/.env
   cp apps/treasury/.env.example apps/treasury/.env
   cp apps/Ember/ember_api/.env.example apps/Ember/ember_api/.env
   chmod 600 .env apps/*/.env apps/Ember/ember_api/.env
   ```

   | File | Keys to fill in |
   |---|---|
   | `apps/armory/.env` | Only the capability keys you use: `SMTP_PASSWORD`, `TEAMS_WEBHOOK_URL`, `TAVILY_API_KEY`, `FIRECRAWL_API_KEY`, `LAYA_URL` (`http://garrison:9111/mcp` to group tickets with the triage agent) |
   | `apps/garrison/.env` | `CLAUDE_API_KEY`, or the keys of the gateway your agents use; `HF_TOKEN` if used; `LAYA_TOKEN` (must equal the root one) |
   | `apps/treasury/.env` | Connection secrets such as Postgres DSNs, if `config_connections.json` references any |
   | `apps/Ember/ember_api/.env` | `BOOTSTRAP_ADMIN_*` (first admin account), `SMTP_*`, `MAIL_FROM_ADDRESS` |

   - The root token reaches every service and overrides any `INTERNAL_API_TOKEN` in a per-app file.
   - Skip `MCP_HOST`, `MCP_PORT`, `LAYA_SERVICE_URL` and service URLs such as `DB_GATEWAY_URL`; Compose sets them. Do
     not use `localhost` for another service.
   - **Laya settings** go in the root `.env`: `LAYA_TOKEN` (the same value as in `apps/garrison/.env`), `LAYA_REPLICAS`
     (default 2) and `LAYA_PORT`. Each replica loads its own copy of the models, and `laya_lb` starts only after a
     replica is healthy; the first start downloads the weights, so allow a few minutes. Do not run LayaAgent's own
     `docker-compose.yml` at the same time: it uses the same port.
   - `apps/Ember/ember_api/.env` must exist before the first start. Compose bind-mounts it, and if it is missing Docker
     creates a directory in its place and ember_api fails. ember_api writes `EMBER_SECRETS_KEY` into it, so keep it
     when you rebuild.

4. **Create the config files git does not hold.** `config_*.json` is gitignored (deploy option 2 copies yours). Compose
   mounts the tracked files under `docker/configs/` over `config_extensions.json`, `config_servers.json`,
   `config_app.json` and `config_connections.json`. For the rest:

   | File | On a fresh clone |
   |---|---|
   | `apps/garrison/configs/config_tuning.json` | Created from its `.example` automatically |
   | `apps/Ember/ember_api/configs/config_pricing.json` | Created from its `.example` automatically |
   | `apps/armory/configs/config_capabilities.json`, `config_email.json`, `config_tickets.json` | Copy each `.example` and fill in `config_email.json` |

   These files are baked into the image at build time, so a change made on the Capabilities page of ember_admin is lost
   when armory is rebuilt. Edit the file instead.

5. **Start:**

   ```bash
   docker compose up -d --build
   ```

6. Open `http://<zima-ip>:5173` and `http://<zima-ip>:5176` from any device on your network.

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
- `apps/armory`, `apps/garrison`, `apps/treasury`, `apps/Ember`
- `docs/deployment.md`

It leaves out other docs, skills, `tools/`, the Python `tests/` folders and `apps/Ember/ember_cli`. `e2e/` and the
`src/*.test.ts` files stay because the web apps' tsconfig includes them. The path lists are at the top of the script;
add a path there when you add a compose service.

Commit `main` first: the script reads committed `main` without touching your working tree, index or branch. The `live`
commit is built on top of the remote tip, so pushes are normal fast-forwards with no force-push. A run with no changes
prints "already up to date". To run it without the menu: `py tools\publish_live.py [--dry-run]`.

### Dashboard tiles

Containers started from the CLI may not show in the ZimaOS dashboard (v1.8.0), and the "import Docker CLI" option in
Custom Install cannot adopt compose containers or build our images. Add external links instead; the containers stay
under compose.

1. In the dashboard, click **+** and choose **Add external link**. The label may differ by version.
2. Add two links, using the box's LAN IP (not `localhost`) so they work from other devices:

   | Name | URL | Icon |
   |---|---|---|
   | Ember | `http://<zima-ip>:5173` | `apps/Ember/ember_web/public/icons/icon-512.png` |
   | Ember Admin | `http://<zima-ip>:5176` | `apps/Ember/ember_admin/public/icons/icon-512.png` |

3. If the dashboard asks for an image URL, use `http://<zima-ip>:5173/icons/icon-512.png` and
   `http://<zima-ip>:5176/icons/icon-512.png`. Avoid `icon-maskable-512.png`; its padding makes the tile look small.

Give the box a fixed IP (a DHCP reservation in the router) so the links keep working. If your version has no external
link option, use a browser bookmark.

## 3. Server Manager

The Server Manager capability (chat id `server`) lists, starts, stops and restarts Docker containers and reads their
logs. It works through the host Docker socket, which `docker-compose.yml` mounts into `armory`
(`/var/run/docker.sock`).

Enable it in `apps/armory/configs/config_capabilities.json`:

```json
"server": { "enabled": true }
```

You can also toggle it on the Capabilities page in ember_admin, but that toggle lives in the container and is lost when
armory is rebuilt, so set the repo file to keep it. The file is gitignored: set it on the box, or push it with deploy
option 2.

Tools: `tool_srv_listApps`, `tool_srv_startApp`, `tool_srv_stopApp`, `tool_srv_restartApp`, `tool_srv_readAppLogs`,
`tool_srv_getAppLogs`. Starting or restarting an app also starts a watcher that emails the person who started it when
the app crashes or logs errors. See `apps/armory/src/capabilities/server_manager/README.md`.

**Security**

- The Docker socket is root on the host. Anyone who can call the `tool_srv_*` tools can control every container.
- Server Manager lists every container on the host, not only Citadel's. On ZimaOS that includes your other apps.
- Keep `INTERNAL_API_TOKEN` secret. Do not publish armory's port 8010.
- Keep `server` disabled where you do not need it.

**Checking it works.** With the stack up and `server` enabled, ask the assistant to list apps, or call
`tool_srv_listApps`. It should return the `citadel-*` containers as `running`. If it reports
`Could not reach Docker from this process`, the socket mount is missing; recreate armory with
`docker compose up -d armory`.

## 4. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `set INTERNAL_API_TOKEN in .env` | The root `.env` is missing or empty. |
| `path ".../LayaAgent" not found` | `LayaAgent` is not next to `Citadel`. See first-time setup, step 2. |
| `.env` files seem to be missing | They are hidden dotfiles. Run `ls -la apps/armory`. |
| `scp` will not log in | Check `DEPLOY_HOST` and that the folder exists. Run `ssh <host>` by hand to test. |
| `openssl: command not found` | Use the `/dev/urandom` command in first-time setup, step 3. A failed `echo` leaves an empty `.env`, so run it again. |
| ember_api fails and `apps/Ember/ember_api/.env` is a directory | Compose created it because the file was missing. Run `rmdir apps/Ember/ember_api/.env`, then `touch apps/Ember/ember_api/.env`, then start again. |
| UI loads on the box but not on another device | Overlay not used. Check `COMPOSE_FILE` in the root `.env`, or add `-f docker-compose.zima.yml`. |
| Overlay still binds `127.0.0.1` | Compose older than 2.24 ignores `!override`. Update Compose, or edit the `ports` lines in the main file. |
| Port already in use | Another app uses 5173 or 5176. Change the left side of the port mapping. |
| `permission denied` on the Docker socket | The container cannot read `/var/run/docker.sock`. Check its owner and mode on the host. |
| Capability toggle reverted after a rebuild | It was changed inside the container. Edit `config_capabilities.json` in the repo. |
