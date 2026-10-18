# ember_worker

Runs on your own computer and connects your own Claude Code and Codex CLIs to Ember's Forge page. It uses the logins you already have in those CLIs and talks to `ember_api` over an outbound WebSocket, so it opens no inbound port. Ember never receives a login or subscription token, only the text of the chat.

Design: `docs/superpowers/specs/2026-10-18-forge-design.md`.

## Requirements

- Python 3.11 or newer.
- The `claude` CLI, logged in, for a Claude worker.
- The `codex` CLI, logged in, for a Codex worker.

## Setup

1. Run `run.bat` once. It builds `.venv_ember_worker` and installs this project.
2. On the Forge page, make a worker (pick Claude or Codex and a label). The page shows a pairing token once.
3. Pair it: `run.bat pair <ember_url> <token> --provider claude`. Repeat with `--provider codex` for a Codex worker. If the CLI cannot report your plan, add `--plan "<plan name>"`.
4. Run `run.bat` to connect every paired worker. Keep it running while you chat.
5. `run.bat status` shows the Ember address, whether each CLI is logged in, its plan and whether it is paired. It never prints a token.

## Modes

The group's mode on the Forge page decides what a worker may do.

- Claude maps Ask, Accept edits, Plan and Full auto to Claude Code's `default`, `acceptEdits`, `plan` and `bypassPermissions` modes. For anything the mode does not allow, the Forge page shows an Allow/Deny card and the worker waits for your answer.
- Codex cannot ask, because `codex exec` is non-interactive. Ask and Plan run in the read-only sandbox, Accept edits in `workspace-write` and Full auto in `danger-full-access`.

## Limits

- Anthropic gives paid plans a separate monthly Agent SDK credit for Agent SDK and `claude -p` use. A Claude worker may draw on that credit instead of your normal plan limit. Check the current size on Anthropic's help page.
- Anthropic does not allow offering a claude.ai login or Pro/Max limits to other people. Run only your own worker, for your own use.
- Plan names are whatever the CLI reports. An administrator lists the eligible plans in Ember, so a plan that shows as `unknown` in `status` can be set with `--plan` when you pair.
- Not yet checked against a logged-in Claude or Codex CLI: the `subscriptionType` field of `claude auth status` and Codex's plan claim. If `status` shows `unknown` while logged in, use `--plan`.

## Config

- `configs/config_worker.json`: `url` (the address of ember_api), `heartbeat_seconds`, `plan_override`.
- `.env`: `EMBER_WORKER_TOKEN_CLAUDE`, `EMBER_WORKER_TOKEN_CODEX`.

Both files are ignored by git. `configs/config_worker.json.example` and `.env.example` are their committed twins; a missing config is made from its example. `run.bat pair` writes both files.

## Tests

```bash
.venv_ember_worker/Scripts/python.exe -m pytest -q
```
