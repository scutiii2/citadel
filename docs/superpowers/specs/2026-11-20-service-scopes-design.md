# Citadel service scopes and limits

Status: AGREED on 2026-11-20 and audited against the code the same day ([audit](../plans/2026-11-20-scope-audit.md)). Nothing is implemented. This version replaces the first draft; it reverses parts of Plan 14 (tool connections in Armory), Plan 15 (Instance Brain in Armory) and commit `983d0623` (gateways as own stacks). No users exist yet, so no data is migrated: everything old is pruned.

## Goal
Give every service one purpose, a list of what it must never own, and limits for growth. The stack starts and runs on its own.

## Principles
1. **One owner per data set.** One service stores it and serves the tools for it.
2. **Dependencies point one way.** Stronghold and Legion call Armory. Armory never calls Stronghold and holds no durable data.
3. **Start without dependencies.** See "Start rule".
4. **Guards fail closed.** See "Guards".
5. **Tools are placed by a rule.** See "Tool placement".
6. **Models only through Legion.** No service calls a model, a gateway, Laya, Jev or a provider directly. Legion is the only caller of the stack gateways. Ticket triage, titles, tags and compaction run as Legion agents. Rule from the user, 2026-11-20.

## Scopes

| Service | Owns | Never owns | Depends on |
|---|---|---|---|
| Portcullis | Identity and access: accounts, roles, permissions, sessions, lockout, outside-client records (key, allowed services, rate limit, spend cap, audit log), allow/deny list (builds on the existing IP filter). The only outside entry. Passes browser streams (audio, attachment content, dictation) to Stronghold. | User content. Tool tokens. Gateway access. | Treasury |
| Legion | Agent definitions and the per-turn runtime: persona, tone, purpose, tool scope, guardrails, loop and budget limits, roles. All MCP connections to outside servers (instance-wide). The only caller of the stack gateways. | Data kept between requests (usage JSONL files stop being a store). Provider keys. | Stack gateways, Armory, Stronghold's MCP server, Treasury catalog |
| Armory | Generic tools open to any agent: pdf, media, search, scrape, git, password and TOTP, server manager. Its own settings. | Any user data. Tickets, notes, memory, skills, brains, usage. Connection records. Extensions proxy. | Nothing for data |
| Stronghold | User content: chats, Brain, tickets with triage, usage and caps, shares, attachments, templates, turn engine. Its own MCP server for Citadel-only tools. REST connections to outside tool services (Bard, Scribe, Reader). Per-user private extensions. | Credentials, roles. | Armory, Legion, Treasury, Portcullis (permissions per request) |
| Treasury | Databases, connections to outside databases, the service catalog (see below), discovery. Closed to the stack. | Service tokens. Business logic. | Nothing |
| Stack gateways | ConversationGateway and DecisionGateway instances: model access, provider keys. | Outside access. | The providers |

## Start rule
- A service starts whatever the state of its dependencies. Connections are lazy and retried in the background; addresses are looked up per call. Registration in Treasury is a background task.
- `/health` is up while the process runs. `/ready` lists each dependency (and each origin of an outside service) with state: configured, reachable, last error. It never fails the container. Admin apps show it.
- Docker `depends_on` becomes start-order hints only.

## Tool failure codes
A tool that cannot reach a dependency returns an error with a number, name, dependency, `retryable` flag and short message, e.g. `[1002] treasury unavailable`.

| Code | Name | Retryable |
|---|---|---|
| 1000 | `TOOL_INTERNAL` | No |
| 1001 | `DEP_NOT_CONFIGURED` | No |
| 1002 | `DEP_UNAVAILABLE` | Yes |
| 1003 | `DEP_TIMEOUT` | Yes |
| 1004 | `DEP_AUTH_REJECTED` | No |
| 1005 | `DEP_ERROR` | Maybe |

Legion's loop guard reads `retryable`. Capability-specific enums (pdf, media) stay for their own codes.

## Guards
A guard answers "may this happen?" and refuses when it cannot decide. Test: if the check failed and the action went ahead, could it cost money, leak data or do damage? Yes means guard. Known guards: Stronghold usage caps (503), Legion tool approval, Portcullis permission checks, login lockout, the outside-client allow/deny list and spend caps, `brain.global.write`. The service still starts; only the guarded action is refused.

## Tool placement
Stronghold serves a tool, as its own MCP server, when any is true: it reads or writes data Stronghold owns; it needs the asking account's identity or Citadel permissions; it has no meaning outside Citadel. Armory serves a tool when all are true: it works on its input or an external system; it touches no Citadel user data; it is safe to expose to outside agents. A generic-sounding tool that needs Stronghold data goes to Stronghold. No exceptions (tickets moved to Stronghold). Legion connects to both.

## Brain (Stronghold)
Replaces Armory's memory, notes and skills capabilities, Obsidian brains, and Plan 15.
- **Brain** is the main capability. Personal, plus one **global brain**.
- **Short-term memory:** a bounded stack per chat; a chat inside a project also has the project's stack (projects do not exist yet; records carry a reserved `scope` field). Never visible to other chats. Near full, the user is warned that it needs compaction; it compacts on the next prompt, or the user compacts manually. Compaction is a Legion agent call. Overflow drops the oldest item and keeps pinned ones.
- **Long-term memory:** Markdown files in an admin-set brain folder (confined root, subfolder per account, deleted with the account), readable by all the account's chats and projects. Built-in RAG: keyword (BM25) first; vectors later through a Legion embedding route (gateway support not checked). Turns search own plus global.
- **Skills** are part of the Brain (learned procedures, success counts). Imported skills start inactive with fresh counts.
- **Records:** id, owner, title, body, tags, `source` (manual, automatic, shared), `edited`, original text kept for revert, revision, timestamps. Automatic records show a warning that editing may break the agent that uses them.
- **Agent access:** agents read every file. User-created files are read-only for agents by default (user may allow edits per file); agent-created files are editable by the agent. Agents propose moving short-term items to long-term; the user accepts.
- **Global brain:** one shared long-term folder (files and skills) read by all accounts and agents, read-only for agents. Writing and reviewing incoming shares need `brain.global.write` (Administrator by default). Results are labelled by source; own files rank first on ties. The write UI warns not to put private data there.
- **Sharing fragments:** a fragment is a file, a section, a skill or a short-term item. The sender picks a fragment and a recipient (any account by username, with a per-recipient block list, or the global brain). Stronghold stores a frozen snapshot, revocable before accept. The recipient imports or declines; import makes an editable copy with `source: shared` and the sender shown. Global shares wait in a review queue for a `brain.global.write` holder. Nothing lands without consent, agents never import, imported text is untrusted, tags and links to private files are dropped. Limits and audit as settings and log entries. Outside clients cannot share.
- **Settings** in Stronghold's `settings.db` with built-in defaults: record limit (default 20,000 characters), stack size, per-account quota, brain root, share limits.
- **Obsidian** is removed for now; it may return as an MCP extension in Legion or a private extension.

## Armory
- Stateless means no durable data of its own; only its settings stay.
- Pdf and media outputs are short-lived downloads: Armory holds the result, returns a link with an expiry (1 hour), Stronghold saves it only when the user asks, and the client shows the time left. Today: files live 6 hours on disk, downloads 10 minutes in memory with 5 MB and 50 MB caps; media exceeds those, so the caps are revisited at build time.
- Connection records, the REST façade and the Connections page from Plan 14 are removed. Email delivery audit is owner data: move to Stronghold or drop (open).

## Outside services and the catalog (Treasury)
- **Registered:** services we run or host, shared by the instance and called by a stack consumer: Bard, Scribe, Reader, Lens, Mimic, and the stack gateways. **Not registered:** provider APIs, SMTP, Firecrawl, Postgres/Firestore, private extensions, Treasury itself. Laya and Jev stay in DecisionGateway's own config. MCP connections are entered in Legion, REST connections in Stronghold.
- **Shape:** a service group with a hidden service id, holding origin rows with origin ids. The name is a label. Consumers store ids and resolve an origin id to an address with `catalog.outside_origin(origin_id)`. Each consumer keeps its own ordered origin list. Citadel's five services keep fixed names. The hard-coded name list in `treasury/src/service_catalog.py` becomes data.
- **Form:** origin first (path split off; no credentials, query or fragment). Found: the group name fills in. Not found: the user names it; a new name makes a group, an existing name adds the origin. Citadel names refused; group names unique. Treasury down: save refused with 1002.
- **Deletes and renames:** only in Treasury admin. Consumers remove only their own tokens, overrides and lists. `used_by` by service id is listed in the delete confirmation. Pins beat auto-registered entries.
- **Tokens and backups:** Treasury stores no tokens. Each consumer keeps a parent token and an ordered list of `{origin id, token override?}`; a token goes only to an origin in its own list. Failover only on connection failure or timeout (1002, 1003), never on a 4xx; return to the primary when healthy; one operation stays on one origin.
- Discovery: Treasury probes known compose names and health endpoints. No Docker socket mount.

## Stack gateways
- Same repo and image as the standalone gateways, run with a Citadel compose profile (reverses `983d0623`; standalone copies stay for other projects).
- Provider keys in the main `.env`, passed by name to only these two containers.
- No host port, a private `llm_net` joined only by Legion and the gateways, only Legion's token accepted. Portcullis has no route.

## Outside clients and access levels
Portcullis holds client records (key, allowed services, rate limit, spend cap, audit log), not user accounts. Each client has its own budget, enforced at Portcullis as a fail-closed guard fed by gateway usage reports. A client calling Stronghold gets its own memory namespace. Two outside levels: Legion (stateless agent) and Stronghold (agent with memory). Outside clients cannot reach the model level or share brain fragments.

## Changes from today
- Legion: no memory store existed; point `memory_recall.py` and `skill_recall.py` at Stronghold's Brain. Hold the outside MCP list. Replace usage JSONL as a store with per-request usage reports.
- Armory: remove memory, notes, skills, tickets, usage, Obsidian, connections, extensions proxy and Brain admin page; add short-lived downloads.
- Stronghold: add MCP server, Brain (short-term, long-term, global, shares, RAG), ticket and usage tools, REST connections and Tool services page again, dictation relay.
- Portcullis: client records, allow/deny list, budgets; stop holding tool tokens; remove the Brain proxy routes.
- Treasury: catalog as data, discovery.
- All services: start rule, error codes, `/ready`.
- Compose: gateway instances, `llm_net`.
- Reverses Plan 14 and Plan 15 work and `983d0623`.

## Order
1. Docs (this spec and the vault notes).
2. Treasury catalog as data, Legion and Stronghold connection forms.
3. Stronghold Brain and MCP server; Armory tools removed.
4. Gateway instances in the compose.
5. Portcullis clients and allow/deny list.
6. Start rule, error codes and `/ready` across services (alongside 3 to 5).
