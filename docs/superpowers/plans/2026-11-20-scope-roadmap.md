# Scope revision roadmap

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md). **Audit:** [2026-11-20-scope-audit.md](2026-11-20-scope-audit.md).

The spec covers independent subsystems, so it is built as separate plans. Each plan ends with working, tested software and is written in full just before it is built, so its code matches the repo at that time. Plan 16 is written now.

| Plan | Delivers | Needs | Reverses |
|---|---|---|---|
| 16 | Treasury outside-service catalog (groups, origins, ids, `used_by`) and the shared client lookup. [Written](2026-11-20-plan-16-outside-service-catalog.md) | nothing | nothing |
| 17 | Treasury Admin page for outside groups (rename, delete with `used_by`; adding stays in the consumer forms) and Portcullis proxy routes. [Written](2026-11-20-plan-17-outside-admin-page.md) | 16 | nothing |
| 18 | Legion: MCP connections by origin id, origin-first form, parent token and per-origin overrides, ordered list, failover on connection failure or timeout. [Written](2026-11-20-plan-18-legion-origin-connections.md). The Armory extensions proxy itself goes in Plan 22 | 16, 17 | nothing yet |
| 18b | Legion: agents see tools of the other MCP connections (explicit `tools.allow`, exact-name calls, roster and glob checks). [Written](2026-11-20-plan-18b-tool-discovery.md) | 18 | nothing |
| 19 | [Written](2026-11-20-plan-19-stronghold-tool-services.md) Stronghold: REST connections for Bard, Scribe, Reader (same form and token model), Tool services page, dictation relay; Portcullis streams go to Stronghold | 16, 17 | Plan 14 |
| 20a | [Written](2026-11-20-plan-20a-stronghold-mcp-short-term-memory.md) Stronghold MCP server skeleton (Legion-only `/mcp`, built-in Legion connection) and short-term memory (per chat, stack bound, compaction as a Legion agent call, warning near full); backend and Portcullis routes only | 18 | Armory memory (removed in 22) |
| 20b | [Written](2026-11-20-plan-20b-long-term-brain.md) Long-term Markdown brain (backend and Portcullis only): confined folder per account, records with source/edited/revert, keyword (BM25) search, agent read-only rule, five MCP tools, live brain settings route | 20a | Armory notes, Plan 15 (removed in 22) |
| 20c | [Written](2026-11-20-plan-20c-skills-and-recall.md) Skills in the Brain (Markdown files in the account folder, three Stronghold MCP tools, `/skills` routes re-pointed); Legion `memory_recall`, `skill_recall` and skill learning call Stronghold; Ember's allow list cut over; no migration of Armory skills | 20b | Armory skills |
| 20d | [Written](2026-11-21-plan-20d-global-brain-and-sharing.md) Global brain (`_global` folder, files and skills, read-only for agents, `brain.global.write`), sharing of a file, section, skill or short-term item as frozen snapshots with accept, decline, revoke, review queue and block list, live sharing limits, agents read global results, backend and Portcullis only | 20b, 20c | none |
| 20e | [Written](2026-11-21-plan-20e-ember-short-term-memory-panel.md) Ember Memory control in the chat header: items with source, pin, remove, add, near-full and full warnings, Compact now; front end only (`apps/ember`) | 20a | none |
| 20f | [Written](2026-11-21-plan-20f-ember-notes-file-browser.md) Ember Notes page as the long-term file browser (folders, search, create, edit with conflict handling, restore original, agent-edit switch, quota line with near-full and full warning); front end only (`apps/ember`); the old private-notes page, its Laya tags and the Obsidian publishing panel leave Ember | 20b | Ember private-notes page |
| 20g | [Written](2026-11-21-plan-20g-ember-sharing.md) Ember sharing (front end only): share a file, one section, a skill or a short-term item to an account or the global brain, a Shares page with the inbox, review dialog (keep, decline, block), sent list with withdraw, and blocked accounts; share buttons in Notes, Skills and the memory panel | 20d, 20f | none |
| 20h | Stronghold Admin "Brain settings" page: short-term, long-term and sharing limits, brain root shown | 20b, 20d | none |
| 20i | Agent proposals from short-term to long-term memory (Stronghold MCP tool and store) with an accept inbox in Ember | 20a, 20b, 20f | none |
| 20j | Remove Stronghold's Treasury notes (`/notes` and its Laya tag routes), the `/memory` routes, their Portcullis proxies and Ember's Memory page. `/skills` stays: it is the live skills review built in 20c (earlier text listed it for removal; change it if the skills review moves) | 20f, 20i | Stronghold notes, `/memory` |
| 20k | Ember global brain: browse and search the global files and skills (everyone), write and edit them and review the incoming share queue with `brain.global.write`; front end only | 20d, 20f, 20g | none |
| 21 | Tickets and usage tools move to Stronghold's MCP server; ticket data in Stronghold | 20a | Armory tickets and usage |
| 22 | Armory cleanup: remove moved capabilities, Obsidian, connections and Brain admin page; short-lived downloads (1 hour) with expiry shown in the client | 18 to 21 | Plan 14 façade |
| 23 | Gateway instances in the Citadel compose, `llm_net`, named key passing, Legion-only token | none | `983d0623` |
| 24 | Portcullis outside-client records, allow/deny list on the IP filter, per-client budget as a fail-closed guard | none | none |
| 25 | Start rule everywhere: error codes 1000 to 1005, `/ready`, `depends_on` as hints, Treasury discovery | any | none |

Order: 16, 17, then 18 and 19 and 23 and 24 may run in parallel (different services). 20a to 20d follow 18. 22 comes last of the data moves. 25 may run alongside.

## Open checks before the plans that need them
- Plan 18 and 19: confirm Bard and Scribe serve MCP and REST on one origin (READMEs confirm Lens, Reader, Mimic only).
- Plan 20b ships BM25 keyword search. Revisit gateway embedding support when vector search enters scope.
- Plan 22: sizes of media files against the download caps.
