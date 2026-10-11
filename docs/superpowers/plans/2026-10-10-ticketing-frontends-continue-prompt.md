# Prompt: continue the unfinished ticketing front-ends worktree (paste into a new Codex session)

Paste everything below the line into a new Codex session. Start it **in the existing worktree** `C:\Users\User\.codex\worktrees\3ae8\MCPServer` (branch `feat/ticketing-frontends`) so the finished work is kept. If Codex insists on a fresh worktree, tell it to `git switch feat/ticketing-frontends` (the branch already exists) instead of creating a new branch.

State when this prompt was written (2026-10-11): the branch has ONE commit on top of an older `main`: `280ed4f feat(ember-web): tickets client` (plan Task 1: `TicketsClient.ts`, its test, `utils/tickets.ts`). The working tree is clean. Tasks 2 to 6 are not started. `main` has moved on since, including changes to files this work touches.

---

You are continuing an approved, test-first plan in an existing Vue 3 + TypeScript repo. A previous session finished Task 1 and stopped. Pick up at Task 2. This is UI work and the owner has a standing rule: **before each task you propose it and wait for approval.** Follow that rule exactly; it is part of the job.

## Repo and documents

- Repo root: the worktree you are in (a git worktree of `D:\User\Documents\Programming\Python\MCPServer`). Branch: `feat/ticketing-frontends`.
- Read first, in this order:
  1. `AGENTS.md` (repo root), `apps/Ember/ember_web/README.md`, `apps/Ember/ember_admin/AGENTS.md`, `apps/Ember/ember_admin/README.md`.
  2. The repo's UI conventions: `.claude/skills/ember-design-system/SKILL.md` (with its `tokens.css` and `components.md`) and `.claude/skills/ember-feature-scaffold/SKILL.md` (sections 3 and 5). Documentation only; do not edit anything under `.claude/skills/`.
  3. The spec: `docs/superpowers/specs/2026-10-10-ticketing-system-design.md` (sections 4 and 5).
  4. The plan: `docs/superpowers/plans/2026-10-10-ticketing-frontends.md`. It has 6 tasks: Part A ember_web (Tasks 1 and 2), Part B ember_admin (Tasks 3 to 6). **Task 1 is already done and committed; start at Task 2.** The plan is the source of truth for code and structure.
- ember_api's ticket routes already exist: read `apps/Ember/ember_api/src/routes/tickets.py` and `apps/Ember/ember_api/src/services/ticket_gateway.py` to confirm the response shapes the clients assume (`{ tickets }`, `{ ticket }`, `{ groups }`, `{ group }`, a stats dict; create returns `{ ticket, duplicate, group_size }`). If a shape differs from the plan, stop and report instead of guessing.

## Step 0: bring the branch up to date (before proposing Task 2)

`main` has changed since this branch was cut, including `apps/Ember/ember_web/src/router/index.ts`, `src/router/pages.ts`, `src/router/index.test.ts` and `README.md` (the Emberlings to Ascension rename and related work), which Task 2 and Task 6 edit. Do this first, once:

1. `git status` must be clean. Then `git fetch` is not needed (same repo); run `git merge main` (a merge commit, never a rebase).
2. If there are conflicts, resolve them keeping `main`'s version of anything unrelated to tickets. Do not touch the ticket client files from Task 1. Re-run `npx vue-tsc -b --noEmit` and `npm test` in `apps/Ember/ember_web`, and say what you resolved.
3. Check the merged result still has `src/api/TicketsClient.ts`, `src/api/TicketsClient.test.ts` and `src/utils/tickets.ts`, and that `npx vitest run src/api/TicketsClient.test.ts` passes.
4. Report this to the owner, then propose Task 2.

Newer backend facts the plan predates (already on `main`, use them as they are):
- Tickets are owned by the account uid. ember_api sends the display name in `ticket.reporter`; ember_web and ember_admin should show `reporter` as the name. Never show or send the uid from the UI.
- Reporters can add custom tags when filing in chat, but the web form in this plan files only type, title and description. Do not add tags to the ember_web form.

## The approval rule (important)

For every task, in this order:
1. **Propose.** Reply with a short proposal: the task name, the files you will create or change, and any deviation from the plan. Then **stop and wait** for the owner to answer "approved" (or give changes). Do not write or edit any file for that task before approval. Never propose or build several tasks at once.
2. **Implement** the task test-first, exactly as the plan says.
3. **Verify** with the task's commands and report the real output (type-check clean, tests passing).
4. **Hand over.** Report what changed, what was verified and how, and the manual checks the owner should do by hand (the owner tests the UI manually; do not launch browser or Playwright verification agents, and run `npm run test:e2e` only where the plan says to).
5. **Commit** only after the checks pass and the owner agrees, with the plan's commit message. Never push.

## How to work

- Run commands from the app folder (`apps/Ember/ember_web` or `apps/Ember/ember_admin`). Type-check: `npx vue-tsc -b --noEmit` (prints nothing when clean). Tests: `npx vitest run <file>` and `npm test`. If `node_modules` is missing in an app, stop and ask before running `npm install`.
- If a plan step has a mistake (wrong name, a test that is clearly a test bug, a type error, an API that differs from the plan's assumption), fix it minimally, keep the intent, and state the deviation in your proposal or report. Known soft spots: the `URLSearchParams` space encoding in Task 3 (`a b` must produce `a%20b`), the `<dialog>` jsdom polyfill in tests (copy the `beforeAll` from `AccountsPanel.test.ts`), the `SegmentedControl` and `ToggleSwitch` props (they differ slightly between ember_web and ember_admin; read each component first), Task 6's overview test (read the existing overview test file's setup before writing the new cases), and that `radiusScale.test.ts` passes (no literal `px` radii, no hex colors).
- Do not silently weaken a test to make it pass and do not skip a step. If you cannot resolve something after a real attempt, stop at that task and report exactly what failed with the command output.

## Rules for this repo (must follow)

- **Other people's work:** the main checkout holds uncommitted work from others; this worktree should not. Still run `git status` before every commit and stage only the exact paths a task names. If a file you must edit has changes you did not make, do not stage the whole file: tell the owner and let them decide.
- Never read, print or edit `.env`, `.env.*`, `secrets/`, `.secrets/`, or key files.
- Ignore `node_modules`, `dist`, `build`, `test-results`, and old-version zips.
- Do not push, force-push, rebase, amend, or delete branches. `git merge main` in Step 0 is the only history operation allowed besides normal commits.
- Edit instruction files only in `AGENTS.md` (never `CLAUDE.md`).
- UI rules: radius only through `--radius-*` tokens and colors only through the tokens in `src/style.css`; status shown with an icon and a word, never color alone; no `confirm()`, use `ConfirmModal`; ticket text rendered with `{{ }}` (never `v-html`); switches and selects that call the server show only server-confirmed state; `erasableSyntaxOnly` is on (no enums, no constructor parameter properties); pages in `src/views/`, reusable pieces in `src/components/`.
- Code quality: small focused components, clear names, comments that explain intent, no placeholders or TODOs, no dead code. Match the style of neighbors such as `AgentsView.vue` (ember_web) and `AccountsPanel.vue` / `AccountDrawer.vue` (ember_admin).
- Commit messages: as given in the plan, ending with the line `Co-Authored-By: ChatGPT <noreply@openai.com>` (replace with your own agent name if different).

## Out of scope (do not build)

Any ember_api or mcp_server change, attachments, email notifications, a tag editor with a fixed vocabulary, assignee and type filter controls in the admin UI (the client supports them; the plan leaves their controls out on purpose). If you believe a backend change is needed, stop and report.

## Done means

- Tasks 2 to 6 approved, verified and committed on `feat/ticketing-frontends`, one commit each, after the Step 0 merge commit.
- In both apps: `npx vue-tsc -b --noEmit` is clean, `npm test` passes, and `npm run test:e2e` passes (Task 6 step 5).
- The READMEs of both apps describe the Tickets pages (Task 6).

## Final report (reply with this, short)

1. Branch name and the list of commits (`git log --oneline main..HEAD`).
2. Final results: type-check, `npm test` and `npm run test:e2e` for each app.
3. Every deviation from the plan, with the reason, including how the Step 0 merge went.
4. Files you edited that also had someone else's uncommitted changes, and how you handled staging.
5. Anything skipped or unresolved, with the exact error output.
6. The manual checks the owner should do (per page: light and dark, 768 px and 375 px widths, keyboard focus).
