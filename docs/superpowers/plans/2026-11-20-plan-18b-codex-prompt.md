# Prompt for Codex: Plan 18b (agents see tools of Legion's other MCP connections)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 18b in the Citadel repo. Only `apps/legion` changes.

Read these first, in order, fully:
1. `AGENTS.md` (repo root) and `apps/legion/AGENTS.md`. Also read `.agents/skills/aiagent-scaffold/SKILL.md`: it covers agent files, `tools.allow` and gateways, and Task 4 may need one sentence added to it.
2. `docs/superpowers/plans/2026-11-20-plan-18b-tool-discovery.md`. It holds the goal, global constraints, file map and four tasks with test code and implementation code. Follow it step by step; it is a script, not only a design.
3. For background only: `docs/superpowers/plans/2026-11-20-plan-18-legion-origin-connections.md` (merged; it added connections that agents could not yet see), `docs/superpowers/specs/2026-11-20-service-scopes-design.md` and `docs/superpowers/plans/2026-11-20-scope-roadmap.md`.
4. The code you will touch: `apps/legion/src/tools/mcp_client/mcp_upstream.py` (whole file), `apps/legion/src/agents/agent_spec.py` (`ToolScope`), `apps/legion/src/agents/agent_routing.py` (`_live_tool_names`), `apps/legion/agents/shared-extensions.json` (its `bard__*` globs), and the test styles in `apps/legion/tests/test_private_upstream.py` and `test_mcp_upstream_description.py`.

Task: agents see and call tools of connections saved in Legion Admin (for example `bard__tool_bard_speak`) when their `tools.allow` names them. An empty `allow` list must never expose such a connection. Build Tasks 1 to 4 of the plan.

How to work:
- Run `git status` and `git log --oneline -5` first. Plan 18 (`97bb6982` or later) must be on `main`; if not, stop and report. Create branch `plan-18b-tool-discovery` from `main`. One commit per task, with the commit messages the plan gives, each ending with the line `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Before changing anything, run the Legion suite once (`uv run pytest -q -p no:cacheprovider -m "not slow"` from `apps/legion`; fall back to `.venv/Scripts/python.exe -m pytest` if `uv run` fails) and record the pass count and any existing failure in the plan file under a "Baseline" heading. After Plan 18 the count was 1,451 passed, 6 deselected.
- Write each failing test first, run it, see it fail for the stated reason, then implement. Use the test and implementation code in the plan. If a snippet does not fit the real code, fix the snippet, keep the behaviour the test states, and record the change in the plan file under a "Changes found during work" heading. The plan lists three assumptions to check at build time; check each and record the result: (a) `tool_filter.is_blocked` returns False outside a turn context, (b) `types.Tool` accepts `name`, `description`, `inputSchema` as the private-upstream tests use it, (c) `agents/shared-extensions.json` keeps working (its `bard__*` glob matches the Legion connection when one exists, else Armory's proxied tool).
- Preserve behaviour for `main` built-ins and Armory's proxied extensions: run the existing Legion tests (`test_private_upstream.py`, `test_read_only_approvals.py`, `test_plan_mode.py`, `test_memory_recall.py`, `test_skill_recall.py`) after Tasks 1 and 2 to prove it. Private (`u_`) tools must stay unchanged.
- Never read, print or write `.env*`, `secrets/` or key files. Never touch `libs/citadel_auth` or any `src/citadel_auth/` copy.
- Keep each file's existing line endings (CRLF in most source files). Edit with your editor tools, not shell heredocs with escapes (unreliable on this Windows machine).
- Do not push and do not publish. Do not weaken or delete a test that fails for a reason outside your change; stop and report instead.
- Do not add behaviour beyond the plan: no new settings, no UI, no change to the registry or Plan 18 code, no read-only annotation for connection tools, no change to `memory_recall` or `skill_recall` tool names. If you think something is missing, note it in your report instead of building it.
- If the plan and the code disagree, grep for the real users of `main__`, `_PREFIX` and `unprefixed`, follow the code, and record the finding as above. Ask only if you would have to weaken a rule in the plan's "Global Constraints" (explicit allow only, exact name wins, scope and user-block checks before anything is sent).

When done, report per task: commit hash, what changed, test commands with pass counts compared with the baseline, the result of each of the three assumption checks, anything not verified (a real agent turn that calls a tool of a real connection, the shared-extensions agent against a live Bard are known gaps), the "Changes found during work" list, and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
