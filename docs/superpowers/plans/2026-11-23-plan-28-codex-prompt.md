# Prompt for Codex: Plan 28 (invite by email)

Copy everything below the line into Codex, started in `D:\User\Documents\Programming\Applications\Citadel`.

---

You are implementing Plan 28 in the Citadel repo. Four tasks: an Armory email health-check tool, Portcullis changes (invite only by email, automatic verification at registration, verification always required), the `portcullis_admin` Invite member drawer, and the `ember` registration and verify-screen changes.

Read these first, in order, fully:
1. `AGENTS.md` (repo root), the workspace `D:\User\Documents\Programming\AGENTS.md` ("Work pace and testing budget" applies), and the `AGENTS.md` of each app you touch (`apps/portcullis_admin`, `apps/ember`; others if present). For UI also read `.agents/skills/ember-frontend-design/SKILL.md`.
2. `docs/superpowers/plans/2026-11-23-plan-28-invite-by-email.md`. It holds the goal, decisions, exact reason texts, file map, the email template and four tasks with test lists. Follow it step by step.

How to work:
- Run `git status` and `git log --oneline -3` first. Work in the current checkout and branch. No branch, worktree, commit or push.
- No baseline run. Read the code, then edit. Write each failing test first and see it fail for the stated reason. After each task run only the test files the task names, once (commands are in the plan). No full suite, no Docker or compose check, no e2e run, no browser. A run over about 2 minutes: stop and ask.
- If a name, route or file in the plan does not match the real code, fix the plan's guess, keep the behavior, and list it under Findings.
- Hard rules: the invite code is never returned by an API, logged or shown in any admin screen. Health answers use only the fixed texts from the plan, never exception text. The health tool sends no mail. Do not add a migration. Keep `apps/ember_web` untouched. Never read, print or write `.env*`, `secrets/` or key files. No reduced-motion code. `uv` for Python, `pnpm` for Node. No subagents.
- Radius and colors only through the existing tokens; reuse the existing drawer, button and error styles in `InvitesPanel.vue`.

When done, report once: per task what changed (files), the test commands you ran with pass counts, which commands you did not run, "Findings", anything not verified (say plainly that no real SMTP server was contacted and the screens were not opened in a browser), and the vault notes under `D:\User\Documents\Programming\Brain` that need an update (do not edit that repo).
