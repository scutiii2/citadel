# Plan 1: Baseline and Portcullis rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `ember_api` to `portcullis` everywhere it is a live name, with no behavior change and the same tests passing before and after.

**Architecture:** Mechanical rename in one branch. A baseline test run comes first. Folder moves use `git mv`, text changes use one scripted `sed` over a fixed file set, then a leftover grep and the same tests prove nothing else changed. Historical documents keep the old name on purpose.

**Tech Stack:** Python 3.12 with uv and pytest, Vue 3 with pnpm and vitest, Docker Compose, Git Bash.

**Spec:** `docs/superpowers/specs/2026-11-14-citadel-revision-design.md` (phase 0 and phase 1)

## Global Constraints

- Work from `D:\User\Documents\Programming\Applications\Citadel`. Run git only inside this repo, never at the workspace root.
- Use `uv` for Python and `pnpm` for Node. Never `pip` or `npm`.
- No behavior change. Public routes, error shapes, ports and ordering stay the same.
- Keep these names unchanged (precedent: the `mcp_server` → `armory` rename kept code identifiers and env vars): `EMBER_API_PORT`, `EMBER_API_URL`, `EMBER_API_HOST`, the Python setting `ember_api_url`, `EMBER_SECRETS_KEY`, and the database file name `ember_api.db`.
- Do not edit: `apps/ember_web/` (reference only, handled in a later plan), `docs/superpowers/plans/` and `docs/superpowers/specs/` (history), `.superpowers/`, `zip_versions/`, `.cache/`, `node_modules/`, `.venv/`, `dist/`.
- Never read or print `.env*` files.
- No reduced-motion code anywhere (project rule).
- Commit trailer, exactly: `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`

## File Structure

Moved with `git mv`:
- `apps/ember_api` → `apps/portcullis`
- `docker/configs/ember_api` → `docker/configs/portcullis`

Text rewritten (`ember_api` → `portcullis`): every tracked file outside the exclusions above that contains the word, found with the grep in Task 2. Known important ones: `docker-compose.yml`, `docs/deployment.md`, `tools/deploy.bat`, `tools/publish_live.py`, `apps/portcullis/pyproject.toml`, `apps/portcullis/uv.lock`, `apps/portcullis/dev_deploy.bat`, `apps/ember_admin/nginx.conf`, `apps/ember_admin/Dockerfile.dockerignore`, `apps/armory/src/**` comments and docstrings, `apps/ember_cli/**`.

Edited by hand: `apps/portcullis/dev_deploy.bat` and `apps/ember_admin/dev_deploy.bat` (stale path depth), the vault notes in `D:\User\Documents\Programming\Brain\Projects`.

---

### Task 1: Branch and baseline

**Files:**
- Create: `docs/superpowers/plans/baseline-2026-11-14.txt` (test results, plain text)

**Interfaces:**
- Produces: a recorded list of which suites pass before the rename. Task 3 compares against it.

- [ ] **Step 1: Create the branch**

Run: `git checkout -b refactor/portcullis-rename`
Expected: `Switched to a new branch 'refactor/portcullis-rename'`

- [ ] **Step 2: Commit the spec so the tree is clean**

```bash
git add docs/superpowers/specs/2026-11-14-citadel-revision-design.md docs/superpowers/plans/2026-11-14-citadel-revision-roadmap.md docs/superpowers/plans/2026-11-14-plan-1-baseline-and-portcullis-rename.md
git commit -m "docs: add Citadel revision spec and plan 1" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

- [ ] **Step 3: Run the Python suites and record results**

```bash
for app in ember_api armory legion treasury ember_cli; do
  (cd apps/$app && echo "== $app" && uv run pytest -q 2>&1 | tail -3)
done | tee docs/superpowers/plans/baseline-2026-11-14.txt
```
Expected: a `N passed` line per app. Any failure here is pre-existing: write it down in the file and do not fix it in this plan.

- [ ] **Step 4: Run the frontend suites and record results**

```bash
for app in ember_admin legion_admin; do
  (cd apps/$app && echo "== $app" && pnpm test 2>&1 | tail -6)
done | tee -a docs/superpowers/plans/baseline-2026-11-14.txt
```
Expected: vitest summary with `passed` per app.

- [ ] **Step 5: Validate the compose file**

Run: `docker compose config --quiet`
Expected: no output, exit 0. If Docker is not installed, write `compose config skipped` in the baseline file.

- [ ] **Step 6: Commit the baseline**

```bash
git add docs/superpowers/plans/baseline-2026-11-14.txt
git commit -m "docs: record pre-rename test baseline" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 2: Rename folders and rewrite text

**Files:**
- Move: `apps/ember_api` → `apps/portcullis`, `docker/configs/ember_api` → `docker/configs/portcullis`
- Modify: every file listed by the grep in Step 3

**Interfaces:**
- Consumes: Task 1 baseline file.
- Produces: service name `portcullis` (compose service, container hostname `portcullis`, folder `apps/portcullis`, volume `portcullis_data`). Later plans refer to these names.

- [ ] **Step 1: Move the folders**

```bash
git mv apps/ember_api apps/portcullis
git mv docker/configs/ember_api docker/configs/portcullis
```
Expected: no output. Git tracks ignored files like `.venv` and `data` as not moved, so they stay behind in `apps/ember_api` if it still exists.

- [ ] **Step 2: Carry over untracked local files**

```bash
ls apps/ember_api 2>/dev/null
```
Expected: either `No such file` or a list of ignored items (`.venv`, `data`, `.env`, `.cache`, `node_modules`). Move each that exists with `mv apps/ember_api/<name> apps/portcullis/<name>`, then `rmdir apps/ember_api`. Do not open `.env`. The old `.venv` has absolute paths inside, so delete it and run `uv sync` in `apps/portcullis` instead of moving it.

- [ ] **Step 3: List the files to rewrite and read the list**

```bash
grep -rIlw \
  --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=dist --exclude-dir=__pycache__ \
  --exclude-dir=zip_versions --exclude-dir=.git --exclude-dir=.cache --exclude-dir=.superpowers \
  --exclude-dir=plans --exclude-dir=specs --exclude-dir=ember_web \
  "ember_api" . | tee /tmp/rename-files.txt | wc -l
```
Expected: roughly 80 to 120 files. Open the list and confirm it holds no `.env` file, no `.db` file and nothing under `apps/ember_web`.

- [ ] **Step 4: Rewrite the text**

```bash
xargs -a /tmp/rename-files.txt sed -i -E \
  -e 's#apps/Ember/ember_api#apps/portcullis#g' \
  -e 's#ember_api\.db#@@DBNAME@@#g' \
  -e 's#\bember_api\b#portcullis#g' \
  -e 's#@@DBNAME@@#ember_api.db#g' \
  -e 's#\bember_api_data\b#portcullis_data#g'
```
`\b` does not match inside `ember_api_url`, `EMBER_API_*` or `ember_api_data`, so env vars and the Python setting keep their names, and the last rule renames the compose volume only.
Expected: no output.

- [ ] **Step 5: Fix the stale script path depth**

In `apps/portcullis/dev_deploy.bat` and `apps/ember_admin/dev_deploy.bat`, change the `pushd` line from `"%~dp0../../.."` to `"%~dp0../.."`. These two files still use the depth from the old `apps/Ember/` layout; `armory`, `legion` and `treasury` already use `../..`.

- [ ] **Step 6: Reinstall the Python environment**

```bash
cd apps/portcullis && uv sync && uv lock --check && cd ../..
```
Expected: `uv sync` finishes, `uv lock --check` prints `Resolved ... packages` and exits 0. If it exits 1 the lock still names `ember_api`; run `uv lock` and review the diff, which must only change the root package name.

- [ ] **Step 7: Commit**

```bash
git add -A apps docker docker-compose.yml docs tools
git commit -m "refactor: rename ember_api to portcullis" -m "Folder, compose service, volume, scripts, docs and comments. Env vars, the ember_api_url setting and the database file name keep their names." -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```

---

### Task 3: Verify nothing else changed

**Files:**
- Modify: none expected. Fix only what a check below reports.

**Interfaces:**
- Consumes: baseline file from Task 1.

- [ ] **Step 1: Leftover grep**

```bash
grep -rInw \
  --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=dist --exclude-dir=__pycache__ \
  --exclude-dir=zip_versions --exclude-dir=.git --exclude-dir=.cache --exclude-dir=.superpowers \
  --exclude-dir=plans --exclude-dir=specs --exclude-dir=ember_web \
  "ember_api" . | grep -v "ember_api\.db"
```
Expected: no output. Any line printed is a live reference the rewrite missed; fix by hand.

- [ ] **Step 2: Compose still valid and names line up**

```bash
docker compose config --quiet
grep -n "portcullis" docker-compose.yml
```
Expected: first command silent. Second shows the `portcullis:` service, `build: ./apps/portcullis`, `./docker/configs/portcullis/app.json`, `./apps/portcullis/.env`, `portcullis_data`, `EMBER_API_URL: http://portcullis:29601` and `depends_on` lines in `ember_web`, `ember_admin`, `legion_admin`, `armory`.

- [ ] **Step 3: nginx upstream renamed**

Run: `grep -n "proxy_pass" apps/ember_admin/nginx.conf apps/legion_admin/nginx.conf`
Expected: `http://portcullis:29601` in both. If `legion_admin` still names `ember_api`, it was missed by an exclusion; fix by hand.

- [ ] **Step 4: Rerun every suite and compare with the baseline**

```bash
for app in portcullis armory legion treasury ember_cli; do
  (cd apps/$app && echo "== $app" && uv run pytest -q 2>&1 | tail -3)
done
for app in ember_admin legion_admin; do
  (cd apps/$app && echo "== $app" && pnpm test 2>&1 | tail -6)
done
```
Expected: the same pass counts as `docs/superpowers/plans/baseline-2026-11-14.txt` (the `ember_api` entry now reads `portcullis`). A different count means the rename changed behavior: stop and find the cause before going on.

- [ ] **Step 5: Frontend build still works**

Run: `cd apps/ember_admin && pnpm build && cd ../..`
Expected: `vue-tsc` and `vite build` finish with no errors.

- [ ] **Step 6: Optional image build**

Run: `docker compose build portcullis`
Expected: `Image citadel-portcullis Built`. Skip if Docker is not running and say so in the commit message of Task 4.

- [ ] **Step 7: Commit any fixes**

```bash
git add -A apps docker docker-compose.yml docs tools
git commit -m "fix: finish portcullis rename leftovers" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
```
If Steps 1 to 6 needed no fix, skip this step.

---

### Task 4: Vault and agent docs

**Files:**
- Modify: `D:\User\Documents\Programming\Brain\Projects\Citadel.md`, `ember_admin.md`, `ember_cli.md`, `ember_web.md` (links only)
- Move: `D:\User\Documents\Programming\Brain\Projects\ember_api.md` → `portcullis.md`
- Modify: `D:\User\Documents\Programming\Brain\index.md`, `log.md`
- Modify: `AGENTS.md` (this repo) if it names `ember_api` (it does not today; check)

**Interfaces:**
- Consumes: the rename from Task 2.

- [ ] **Step 1: Read the vault rules**

Read `D:\User\Documents\Programming\Brain\AGENTS.md` fully (frontmatter, link and index rules). Follow them; a hook blocks bad notes.

- [ ] **Step 2: Rename the project note**

```bash
cd "D:/User/Documents/Programming/Brain/Projects"
mv ember_api.md portcullis.md
```
Edit `portcullis.md`: set `repo:` to `Applications/Citadel/apps/portcullis`, add `aliases: [ember_api]` to the frontmatter so the 41 old `[[ember_api]]` links in older notes keep resolving, and add one line under the title: `Renamed from ember_api on 2026-11-14.`

- [ ] **Step 3: Update live notes only**

In `Citadel.md`, add a row to the rename table: `| ember_api | portcullis |`, change the Components table row and the ports and architecture mentions of `ember_api` to `portcullis`. In `ember_admin.md`, `ember_cli.md` and `ember_web.md` change only the `[[ember_api]]` links to `[[portcullis]]`. Leave decision notes and dated rows alone: the vault keeps old names there on purpose.

- [ ] **Step 4: Update index and log**

In `Brain/index.md` rename the `ember_api` entry to `portcullis` with the same one-line summary. Append to `Brain/log.md`:

```
## [2026-11-14] lint | rename ember_api to portcullis
Renamed Projects/ember_api.md to portcullis.md (alias kept). Updated Citadel, ember_admin, ember_cli, ember_web, index.
```

- [ ] **Step 5: Run the vault validator**

Run: `py "D:/User/Documents/Programming/.claude/hooks/validate_vault.py" --all`
Expected: exit 0, no blocking messages. Fix what it reports.

- [ ] **Step 6: Final commit in the Citadel repo**

```bash
cd "D:/User/Documents/Programming/Applications/Citadel"
git status --short
```
Expected: clean. The vault is outside this repo, so its changes are not committed here.

---

## Self-review

- **Spec coverage:** phase 0 (baseline, branch) is Task 1. Phase 1 (rename of dir, compose, env, docs, vault notes, deploy tools) is Tasks 2 to 4. Env vars are deliberately kept, noted in Global Constraints.
- **Placeholders:** none. Counts in expected output are bounded by the baseline file, not guessed.
- **Names:** `portcullis`, `portcullis_data`, `apps/portcullis`, `docker/configs/portcullis` are used the same way in every task.
