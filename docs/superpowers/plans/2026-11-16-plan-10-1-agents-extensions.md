# Plan 10.1: Account agents and private extensions to Stronghold

Branch: `refactor/stronghold-agents-extensions`. First step of Plan 10 (`2026-11-16-plan-10-turn-engine.md`).

## Result

- Stronghold: `src/agents/accounts.py` + `routes.py` (`/account-agents`: `GET`, `PUT /{id}`, purge) and `src/extensions/` (`service.py`, `probe.py`, `routes.py`: `/user-extensions` list, add, patch, delete, purge, and `GET /for-turn`). Two catalog collections (`account_agents`, `user_extensions`) with purge routes. Header values are encrypted with Stronghold's own `SecretBox`.
- Portcullis: `routes/account_agents.py` and `routes/user_extensions.py` are pass-throughs (login, then `chat.use` or `extensions.personal.manage`) that write the account log line after Stronghold accepts a change. `start_turn` reads the switched-off agents and the private extensions from Stronghold (`/account-agents`, `/user-extensions/for-turn`). Deleting an account purges both domains through the admin purge loop.
- Removed from Portcullis: `account_agent_service.py`, `user_extension_service.py`, `extension_probe.py`, the probe in `app.py` and `deps.py`, and their tests (ported to Stronghold).
- Public `/api/...` paths and bodies are unchanged.

## Deviations from Plan 10

- **`extension_probe` moved too.** Plan 10 left it in Portcullis, but only the private-extension routes used it, and the probe needs the decrypted headers that now live in Stronghold. Stronghold already had the Legion gateway and agent directory (from the tuning plan), so nothing was duplicated.
- Step 10.2 (a Legion client in Stronghold) is therefore mostly done: `AgentGateway`, `AgentDirectory` and `mcp_session` exist in `apps/stronghold/src/agents`. What is left for 10.2 is the turn-specific calls (`ask` with events, `cancel`, `decide`, `answer_question`), which the gateway already has and need tests there.

## Behaviour that changed

- The log line for removing an extension names its slug, not its label (Portcullis no longer reads the extension first).
- The "Enabled/Disabled" log line is written for any `enabled` change request, even when the value did not change.
- Private-extension secrets stay encrypted with Portcullis's old key in the old store only; Stronghold starts empty (no data migration, as decided in Plan 5). Accounts add their private extensions again and switch agents off again.

## Not run

- Stronghold and Portcullis against real Treasury, Legion and Armory. Docker builds.

## Execution notes (2026-11-16)

- Stronghold 605 tests (new: account agents, extension service, probe, routes). Portcullis 1268 passed.
