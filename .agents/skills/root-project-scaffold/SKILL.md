---
name: root-project-scaffold
description: Create or audit a new top-level project directory under apps/ (a new server, service, or standalone application sitting alongside mcp_server/ai_agent) so it follows the same folder-structure convention those already share. Use whenever the user asks to add a new app/server/service to this repo, scaffold a new root-level project, or wants to check whether an existing root folder matches repo convention — even if they only describe it ("I want a new microservice for X", "add another backend next to mcp_server") without naming this skill or "folder structure" explicitly. This is about the project's *top-level shape* (what folders exist at its root) — for what goes *inside* mcp_server's capabilities/, use mcp-capability-scaffold instead.
---

# root_project_scaffold

Every Python project in this repo's `apps/` folder (`mcp_server`, `ai_agent`, `ember_api`,
`chat_cli`, `server_launcher`, `db_gateway`, `chess` and `ascension`;
`PDFMerger` and `MediaDownloader` each hold a Python app and a web app) shares one top-level shape. The three Ember projects sit together in
`apps/Ember/` (`ember_api`, plus the Node apps `ember_web` and `ember_admin`, which have their
own layout - see ember-feature-scaffold); everything else is `apps/<name>/`. A new root-level project must match it, not
invent its own layout — consistency here is what lets `server_launcher.py`,
onboarding docs, and anyone jumping between projects rely on the same
mental map.

## The required shape

Mandatory in every root project:

| Path | What it is |
|---|---|
| `README.md` | What the project does, setup steps, requirements — see apps/armory/README.md as the fullest example |
| `pyproject.toml` | Its own dependencies — each root project is a separate Python environment, never a shared venv |
| `run.bat` | The one launcher, env-var-configured: don't copy the bat per instance, set env vars before calling it (ai_agent goes further: its bat starts a supervisor that runs one child per `agents/<id>.json`). Creates its own `.venv_<project>` on first run |
| `shell.bat` | Opens a terminal with the project's venv active, in the project folder (`cmd /k "call .venv_<project>\Scripts\activate.bat"`); prints a hint and exits if the venv is missing. Copy `apps/Ember/ember_cli/shell.bat` and change the venv name |
| `configs/` | JSON config, each real file gitignored with a committed `.example` twin (`config_x.json` + `config_x.json.example`) |
| `.env`, `.env.example` | The project's one credentials file, in the project root beside `configs/` (no `secrets/` folder). The real `.env` is gitignored; `.env.example` is committed. `ascension`, `mcp_server`, `ai_agent`, `db_gateway` and `chess` follow this |
| `src/` | The actual code |
| `tests/` | Its test suite |

Conditional — add only if the project actually needs it, don't
pre-create empty ones "for consistency":

| Path | When to add it |
|---|---|
| `data/` | Persists runtime data to disk (mcp_server, ember_api have it; ai_agent keeps its registry and usage JSONL under `.data/`; chat_cli keeps nothing, ember_api stores its chats) |
| `docs/` | Documentation beyond the README is substantial enough to split out |
| `migrations/`, `scripts/` | ember_api only: Alembic revisions and its CLIs (`migrate_db`, `backup_db`, `import_chat_app`). A new project with a database may follow it; otherwise use `src/` |
| `web/` | Standalone game UI with its own package manifest and lockfile; build into ignored `web/dist/` and serve it from the game API (see Ascension) |
| `manifest.json` | Public game metadata for Ember registration |
| `logs/` | The project writes its own log files (needs a `logging_setup.py`-style module in `src/`, not an ad-hoc log call) |

Do not invent additional top-level folders (`lib/`, `scripts/`, `bin/`,
`app/`, etc.) — if something doesn't fit `src/`, it likely belongs inside
`src/` as a subpackage instead. If a genuinely new top-level folder seems
necessary, flag it to the user rather than adding it silently, since it
changes the convention for every project after it.

## Adding a new root-level project

(New projects go in `apps/<name>/`, next to the others.)

1. Confirm it's actually a new *project* (its own deployable
   process/environment) and not a new capability/page/agent inside an
   existing one — those go through mcp-capability-scaffold,
   ember-feature-scaffold, or aiagent-scaffold instead.
2. Create the mandatory folders/files from the table above. Copy
   `apps/armory/run.bat` and `apps/armory/pyproject.toml` as starting
   templates — they're the most complete examples — and strip anything
   MCP-specific that doesn't apply.
3. For every config/secret file, write both the real (gitignored) file
   and a `.example` twin with placeholder values, matching how
   `apps/armory/configs/*.json.example` and the root `.env.example` do it.
   Loaders should auto-create a missing real file by copying its
   `.example` (see `apps/garrison/src/core/seed.py`) rather than raising on first run.
4. Write `README.md` covering: what the project does, requirements,
   setup steps, how to run it — model it on `apps/armory/README.md`.
5. Register it with `server_launcher` if it should be startable from there
   (add it with the launcher's Add button; it reads the project's `run.bat`, with
   `REM LABEL:` and `REM DESCRIPTION:` lines for the name and blurb). A
   **long-running service** is registered; an interactive program like `chat_cli`
   (a terminal client, not a server) is not (`REM LAUNCHER: skip`). Give the
   port a variable the bat sets (`set CHESS_PORT=8070`, read by `src/config.py`
   as an override) and add the project to the launcher's `_PROJECT_PORT_ENV` so
   a built launcher exe sees the default port. Pick a free port: 8010 mcp_server,
   8030 ember_api, 8040 pdf_merger, 8060 ascension,
   8070 chess, 8071 db_gateway, 9100+ ai_agent agents.
6. Services reached over HTTP/MCP by other projects must take the shared
   `INTERNAL_API_TOKEN` from a secrets file (`.env` in each project) and, for
   `/mcp`, reject calls without it once set. Never import another root
   project: self-contained means a separate venv and no shared packages
   (see `chat_cli`, which talks to ember_api over HTTP instead of reusing
   its code). Game browser APIs use game-owned bearer sessions: the shared token
   stays server-side for redemption against Ember. Never expose it in the UI.

## mcp_server's dotted variant

`mcp_server` already goes one step further, and a new server that owns per-capability state should copy it: the rule is
**dot-prefixed = untracked runtime state or secrets, plain `configs/` = tracked**. Its root has `.data/`, `.logs/`, `.cache/`
(in place of plain `data/`, `logs/`), a single `.env`, and `configs/`; each capability gets `.data/ .logs/ .cache/ .secrets/ configs/` under
`specifics/<capability_name>/`. An untracked dot-folder needs no `README.md`; a
credentials README that is worth keeping lives in `docs/` (see `apps/armory/docs/secrets.md`); `.env.example` stays tracked. `apps/armory/migrate_state_layout.py` moves an older checkout onto this shape. `ai_agent`, `ember_api` and `chat_cli` use the
plain folder names above.

## Auditing an existing root folder

Walk the table above against the folder in question. Flag:
- A missing mandatory item.
- A config/secret file committed without a `.example` twin, or an
  `.example` twin that's drifted out of sync with the real file's keys.
- A top-level folder not in either table — ask whether it should move
  under `src/` or whether the convention itself needs to grow.
- A conditional folder (`data/`/`docs/`/`logs/`, or mcp_server's dotted equivalents) present but empty/unused
  — likely copy-pasted out of habit rather than needed.

## Verify before calling it done

- `ls` the new project root and confirm it matches the mandatory table
  exactly, with no extra top-level entries.
- Every `configs/*.json` file and the root `.env` has a committed `.example`
  counterpart, and neither the real file nor real secrets are staged in
  git (`git status` — they should show as untracked/ignored, not staged).
- `shell.bat` opens a terminal with the venv active.
- `run.bat` starts the project standalone (not just importable) before
  wiring it into `server_launcher.py`.
