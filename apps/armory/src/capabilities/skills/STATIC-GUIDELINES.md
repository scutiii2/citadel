# capabilities/skills/ static and state files

## `apps/armory/specifics/skills/.data/skills.db`

- Runtime state: a SQLite database created on the first proposal. Gitignored by `/apps/armory/specifics/*/.data/`. Path setting: `MCP_SKILLS_DB_PATH`.
- Tables: `skills` (id, owner (the account uid), title, when_to_use, steps, tools, norm, status, successes, failures, created_at) and `skills_fts`, an FTS5 index over title, when_to_use and steps whose rowid equals `skills.id`.
- Status: `proposed` (written by the assistant, never returned by search), `active` (approved by the user), `retired`. Only `services/skill_store.set_status`, called from the user's side, makes a skill active; no MCP tool can.
- Limits: 80 / 300 / 1200 / 200 characters for title / when_to_use / steps / tools, 20 proposed and 50 active skills per account.
- Contains text a model wrote about how it solved the user's tasks. Protect it like account data. Skill text is never written to the logs.
- Keyed on the account uid like memory. Deleting an account triggers a best-effort purge through `DELETE /skills/owners/{uid}` (internal token required); a failed purge leaves orphaned skills that nothing reads.
