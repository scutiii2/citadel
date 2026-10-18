# Prompt: implement gateway failover (paste into ChatGPT / Codex)

Paste everything below the line. Use an agent that can read and edit files and run commands in the repo (Codex CLI, ChatGPT with a repo connection). A plain chat window without file access cannot do this task.

---

You are implementing an approved, test-first plan in an existing Python repo. Work autonomously, task by task, and report at the end.

## Repo and documents

- Repo root: `D:\User\Documents\Programming\Python\MCPServer` (git repo, branch `main`).
- Read first, in this order:
  1. `AGENTS.md` (repo root), `apps/ai_agent/README.md` and `apps/ai_agent/src/llm/README.md`.
  2. The spec: `docs/superpowers/specs/2026-10-18-gateway-failover-design.md`.
  3. The plan you must execute: `docs/superpowers/plans/2026-10-18-gateway-failover.md`.
- The plan has 9 tasks. The spec is the source of truth for behaviour; the plan orders the work and names files and interfaces. The plan gives interfaces, not full code: read each file before you edit it and match the surrounding style. Where plan and spec differ, the spec wins.

## How to work

1. Create a branch first: `git switch -c feat/gateway-failover`. Do all work there.
2. Execute Tasks 1 to 9 in order. For each task: write the failing test, run it and confirm it fails, implement, run it and confirm it passes, then commit with the message the task gives. One commit per task.
3. Run tests from `apps/ai_agent`: `.venv_ai_agent\Scripts\python -m pytest <path> -q` (if that venv is missing, use `py -m pytest`). After Tasks 5, 6 and 7 run the whole `apps/ai_agent` suite and fix any regression you caused before moving on.
4. Tests must never call a real gateway or need real keys. Fake the SDK the way `tests/test_anthropic_provider.py` and `tests/test_openai_provider.py` do. The `cooldown` dict is process-wide: reset it in each test that touches it.
5. If a plan step is wrong (wrong name, a test that is clearly a test bug, an API that behaves differently from the plan's assumption), fix it minimally, keep the intent, and note the deviation. Do not weaken a test to make it pass and do not skip a step. If you cannot resolve something after a real attempt, stop at that task and report exactly what failed, with the command output.
6. Two design points need care, because they are easy to get wrong: (a) after a gateway switch, thinking/reasoning blocks echoed in earlier messages must be stripped, since their signatures are gateway-specific; (b) retry only the failed round and never run a tool twice. The spec explains both. Cover each with a test.

## Rules for this repo (must follow)

- Do not touch unrelated files. The working tree already holds uncommitted changes from other work (for example under `apps/Ember/ember_api/`, `apps/ai_agent/src/llm/decision.py`, `laya_provider.py`, `triage_flow.py`, `apps/mcp_server/`, and an untracked `0019_starter_roles.py`). Never stage, modify, revert, stash or commit them. Always `git add` only the exact paths your task names. If a file you must edit already has uncommitted changes you did not make, stop and report instead of editing it.
- Never read, print or edit `.env`, `.env.*` (except `.env.example` if a task requires it), `secrets/`, `.secrets/`, or key files.
- Ignore `node_modules`, `.venv*`, `__pycache__`, `dist`, `build`, old-version zips and `zip_versions`.
- Do not run git commands above the repo root. Do not push, force-push, rebase, amend, stash or delete branches.
- Edit instructions only in `AGENTS.md`, never `CLAUDE.md`. Edit skills only in `.agents/skills/`, then run `python sync_skills.py` to copy them; never edit `.claude/skills/` directly. Do not edit anything under `Brain/` or `_ClaudeSkills/`.
- Never add a reduced-motion setting, `prefers-reduced-motion` query or test anywhere.
- Code rules: non-blocking (no blocking I/O on the event loop), small focused modules, clear names, docstrings that explain intent, complete runnable code, no placeholders or TODOs, SOLID and composition over inheritance. Check `catalog_service` for an existing building block before writing a new reusable function or class, and tag new reusable ones with `@catalog` like `src/llm/cooldown.py` does.
- Never log error messages, prompts, tool arguments or results.
- Commit messages: conventional style as given in the plan, ending with the line `Co-Authored-By: ChatGPT <noreply@openai.com>` (use your own agent name if different).

## Out of scope (do not build)

Any change to `apps/Ember/` (ember_api, ember_web, ember_admin), cross-provider fallback, persisting cooldowns, spend-based switching, and enabling fallbacks on any tracked agent file.

## Done means

- All tasks committed on `feat/gateway-failover`, one commit each.
- `pytest -q` in `apps/ai_agent` passes with no new failures.
- `python sync_skills.py --check` reports no drift.
- The six acceptance points at the end of the spec are each covered by a passing test.

## Final report (reply with this, short)

1. Branch name and the list of commits (`git log --oneline main..HEAD`).
2. Final pass/fail counts for the `apps/ai_agent` suite.
3. Every deviation from the plan or spec, with the reason.
4. Anything skipped or unresolved, with the exact error output.
5. What ember_api does with the unknown `gateway_switch` event (Task 7 finding).
6. Anything in the spec or plan you think is wrong or risky that I should review.
