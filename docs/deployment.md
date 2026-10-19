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

2. Copy the repo to the box, for example to `/media/ZimaOS-HD/Apps/Citadel`. Over SSH:

   ```bash
   scp -r Citadel user@zimaos:/media/ZimaOS-HD/Apps/
   ```

   Skip `node_modules` and `.venv` folders to save time.
3. On the box, create `.env` as in section 1 (`INTERNAL_API_TOKEN`).
4. Start with the overlay:

   ```bash
   cd /media/ZimaOS-HD/Apps/Citadel
   docker compose -f docker-compose.yml -f docker-compose.zima.yml up -d --build
   ```

5. Open `http://<zima-ip>:5173` and `http://<zima-ip>:5176` from any device on your network.

Without the overlay the UIs stay on `127.0.0.1` and are not reachable from the LAN.

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
| UI loads on the PC but not on another device | Overlay not used. Add `-f docker-compose.zima.yml`. |
| Overlay still binds `127.0.0.1` | Compose older than 2.24 ignores `!override`. Update Compose, or edit the `ports` lines in the main file. |
| Port already in use | Another app uses 5173 or 5176. Change the left side of the port mapping. |
| `permission denied` on the Docker socket | The container cannot read `/var/run/docker.sock`. Check its owner and mode on the host. |
| Capability toggle reverted after a rebuild | It was changed inside the container. Edit `config_capabilities.json` in the repo. |
