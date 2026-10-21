# Instance and personal Obsidian brains with Notes promotion

Date: 2026-10-21 (Asia/Manila)
Status: Implemented; verification recorded in the three slice plans. Local commit and rebase/merge to `main` requested by the user. Undeployed; live vault validation remains pending.

## Intent and agreed responsibilities

Give Notes, Memory and Obsidian distinct responsibilities while making durable
knowledge available through Citadel. Existing Notes remain intact.

| Area | Responsibility |
| --- | --- |
| Memory | Short personal facts, preferences and defaults used across conversations. |
| Notes | Account-owned captures, drafts, lists and working material; agent access is optional. |
| Instance Brain | One instance-configured Obsidian vault containing shared durable knowledge. |
| Personal Brain | One optional Obsidian connection per account containing personal durable knowledge. |

The user agreed that every signed-in user can read and search the Instance Brain.
Publishing to that brain requires a permission granted by an administrator.
Personal connections and their contents are scoped to their owners. AI suggests
Notes worth promoting; the user chooses what to publish and where.

## Scope and chosen approach

Extend the existing Obsidian capability and Ember Notes rather than introduce a
second knowledge store. Keep Markdown in Obsidian authoritative for published
documents. Store connection metadata and promotion links in Citadel; retrieval
indexes are generated, disposable copies.

Alternatives considered:

- Retain environment-only configuration: least work, but cannot meet live Admin
  settings or personal connections.
- Treat every vault as a private MCP extension: existing connection machinery
  helps, but does not supply consistent indexing, shared access or promotion.
- Add scoped connections to the existing capability: chosen because browsing,
  writes and hybrid retrieval remain behind one Obsidian interface.

Deliver three dependent slices: connection management; scoped retrieval; Notes
promotion including AI suggestions. Each slice receives its own implementation
plan and verification. Automatic background suggestions, bidirectional document
sync and multiple personal connections per account are outside this version.

## Access and destinations

- Instance connection management uses `settings.manage` and its existing verified
  staff rules. Personal connection settings require an authenticated account.
- Add `brain.instance.publish`. Administrators receive it; other existing roles
  receive no automatic grant. It allows shared writes, not connection management.
- Dedicated Instance Brain browse/read/search routes are available to every
  authenticated account under the application's existing account validity rules.
  They do not require opting into the capability in the Supermarket.
- Agent and direct MCP use still obey existing tool-execution permission,
  capability availability, per-user tool switches and tool approvals. Availability
  of a brain does not bypass those controls.
- Personal reads and writes require the caller's immutable account UID. Shared
  writes require `brain.instance.publish` as well as connection write enablement.
  These checks apply to all paths, including MCP tools and conversation auto-save.
- Search accepts `instance`, `personal` or `both`. Writes accept one destination.
  The backend resolves ownership from trusted identity rather than a supplied UID.
- Missing, disabled or failing personal connections produce an explicit error;
  writes never fall back to the Instance Brain.
- Personal privacy means isolation from other product accounts and ordinary admin
  views. It does not imply encryption from the deployment operator, who controls
  Citadel's runtime and encryption key.

## Connection management and runtime changes

Ember Admin gains Instance Brain connection controls; Ember user settings gains
Personal Brain controls. Both provide label, HTTPS endpoint, write enablement,
default publication folder, a write-only API-key input, Test connection, Save,
Disable and connection/index status. Existing credentials appear only as a
configured indicator; leaving the key field unchanged preserves its value.

Ember API owns connection documents in db_gateway and encrypts API keys using its
existing `SecretBox`. Each record has a stable ID, scope, owner UID where personal,
revision, endpoint, settings, encrypted credential and timestamps. The instance
record is unique per deployment; a personal record is unique per owner UID.
The API returns only sanitized metadata to browsers and never exposes stored keys
through read responses, logs, model prompts or tool results.

An authenticated internal resolver in Ember API supplies Armory the authorized
connection snapshot for a trusted requester, operation and destination. Resolution
checks permissions on each operation; caller-supplied scopes never grant access.
Internal access requires the deployment token and fails closed without trusted
identity. Armory holds resolved secrets transiently for requests and indexing.

Save validates and persists the candidate, then advances the revision. Subsequent
operations resolve the saved revision without a process restart. An operation
already dispatched may complete against its original connection; new operations
use the new revision. Disable prevents new operations and cancels indexing work.
An index result or background write from an obsolete revision cannot attach to a
replacement connection. Test connection performs bounded, read-only probes and
does not activate the candidate or write documents.

Credential rotation can reuse an index only after confirming the same source and
authorization scope. Endpoint, source, TLS or authorization changes otherwise
start a fresh index generation. Old content is never served as the replacement
vault. Embedding-model changes also create a new generation.

Connections must be reachable from the backend. A user's desktop loopback address
cannot refer to their desktop from a remote Citadel server. User-supplied endpoints
use connect-time address validation, checked DNS resolution, bounded responses,
HTTPS verification and refused redirects. Private LAN endpoints are allowed;
metadata, link-local and backend loopback targets are refused for personal
connections. An administrator may configure the local instance endpoint.
Deployment network egress controls remain applicable. Certificate trust must be
configured deliberately; personal settings do not offer a global TLS bypass.

## Scoped retrieval

Replace the singleton index runtime with runtimes keyed by connection ID and
generation. Isolate personal index files, caches, refresh state and failures.
Authorize the destination before selecting an index; filtering results after a
shared search is insufficient. Bound active workers and embedding concurrency,
retire idle runtimes, and ensure one unavailable vault does not block another.

Keep existing heading chunking, BM25/vector fusion, wikilink ranking and citations.
Add a remote source adapter using the existing REST list/read operations so users
do not need a server filesystem mount. Recursively enumerate bounded vault paths,
fetch Markdown with existing content limits, hash content and refresh incrementally.
Only a fully completed enumeration may remove unseen documents. Partial scans
retain previous completed documents for the same authorized generation and report
their refresh failure. First indexing can return an explicit indexing state.

The existing read-only mount remains a supported source for the deployment's
legacy instance connection. Changing a remote endpoint cannot silently keep using
an unrelated mount. Mounted sources remain server-provisioned; UI settings cannot
create host mounts or grant arbitrary filesystem access.

Results identify brain scope, connection label, vault-relative path, heading and
refresh status. A search over both brains retrieves authorized candidates from
each and combines ranks with per-source limits; raw vector scores from separate
indexes are not assumed comparable. Failure in one source is identified alongside
results from the healthy source. Citadel does not automatically reconcile
contradictory documents; answers retain their source attribution.

Disconnect revokes retrieval immediately and schedules derived cache/index
removal after active readers close. Account deletion removes its connection,
credentials, suggestions, promotion links and personal derived state. It does not
delete remote Obsidian documents or previously published shared knowledge.

## Manual promotion from Notes

Notes gains Promote to Obsidian when at least one writable destination is
available. The review shows destination, audience, document path and Markdown
preview. A shared destination clearly states that all signed-in users can read it.
Users can edit the preview before publishing. The backend rechecks source owner,
source revision, destination revision and publish permission at submission.

Preserve the original Note. Store a promotion record containing source note ID,
source content hash/revision, destination connection/generation, remote path,
published content hash and date. Keep private source metadata out of shared
documents. The Note displays a link and its publication status; later edits show
that the Note changed since publication. No automatic synchronization occurs.

Creation uses collision-resistant paths and create-only semantics. Each accepted
promotion has an idempotency key and pending record before the remote write.
Concurrent submissions for the same source revision and destination converge on
that record. Repeated requests return the existing successful publication. A
timeout after a possible write triggers reconciliation at the reserved path by
content hash, rather than creating another document. Conflicting content is shown
for review and never overwritten. Remote publication succeeds before a Note is
marked promoted; a local persistence failure remains recoverable through the
pending record. Changed Notes can be promoted as a new version through an explicit
action; this release does not overwrite an existing publication.

## AI promotion suggestions

Start with a user-triggered Suggest promotions action. Send only that account's
eligible Notes to the existing agent interpretation path, without tools, and
record model usage through the existing usage accounting and limits. Armory tools
remain deterministic and do not call models. Suggestions favor durable decisions,
reusable procedures, developed research and stable project knowledge over temporary
lists, incomplete fragments and personal preferences suitable for Memory.

Default eligibility is `agent_readable=true`. A user may explicitly select a private
Note for this review after seeing that its contents will go to the configured AI
provider; that one review does not change its persistent agent-access switch.
Bound each request to 20 Notes and 40,000 total characters. Longer selections
require smaller batches instead of silent truncation. A single Note may use the
existing 20,000-character body limit.

Return structured suggestions: source Note ID and content hash, explanation,
suggested title/folder/tags, proposed destination and editable publication draft.
Validate IDs against the reviewed input, paths through existing path validation,
and destinations against current authorization. Model output is untrusted data.
Suggestion generation performs no Obsidian writes. Users accept or dismiss each
candidate; accepting opens the same promotion review as manual publication.
Personal is the default destination when configured. Shared publication always
requires explicit audience review. A changed Note or connection invalidates its
old suggestion. Dismissals are keyed to Note content and destination so unchanged
items need not be repeatedly suggested. Suggestion failure preserves Notes and
allows ordinary manual promotion.

## Compatibility and rollout

1. Preserve existing Memory behavior and Notes access/save contracts.
2. Treat existing environment configuration as the legacy Instance Brain until an
   administrator saves a managed connection. Do not read or rewrite secret files
   during migration. Managed disablement takes precedence over environment fallback.
3. Extend existing Obsidian tools with optional destination scope, preserving
   legacy instance behavior for calls that omit it. Every shared write receives
   the new publish check. Anonymous access to shared knowledge is refused.
4. Keep the existing conversation auto-save toggle and migrate its meaning to an
   explicit destination. Existing enabled chats retain `instance`, subject to the
   new publish permission; permission loss disables the write with a visible
   explanation. New opt-ins select a destination. Never redirect an existing chat
   to a personal vault silently. Update web, API and CLI contracts together.
5. Add permission migration, connection/promotion routes, account cleanup, usage
   records and generated-state documentation with their respective slices.

## Acceptance and verification

- Any valid signed-in account can browse/read/search an enabled Instance Brain;
  unauthenticated requests fail. Existing tool permissions still govern agent use.
- Only authorized publishers can write shared knowledge through any route/tool;
  admins manage instance settings separately. Personal records and indexes cannot
  be selected by another account, including forged IDs or MCP arguments.
- Saving or disabling a connection takes effect without restart; concurrent saves,
  active requests and stale index workers cannot mix vault generations.
- API keys remain encrypted at rest and absent from read responses, logs and model
  inputs. Endpoint tests cover DNS changes, refused redirects and blocked targets.
- Remote and mounted indexing share retrieval behavior; incomplete scans, removals,
  offline vaults and first-index states are exercised without mixing owners.
- Manual promotion preserves Notes, validates permissions and revisions, avoids
  duplicate writes under retry/concurrency and recovers from partial completion.
- AI review honors note visibility, explicit private-note selection, batch limits,
  usage limits, output validation, changed content and dismissals.
- Browser flows cover instance settings, personal settings, review, shared audience,
  failures and retained drafts. Run relevant API/Armory/Garrison tests, frontend
  type checks/builds and focused browser flows for each implementation slice.
- Verify legacy tools, conversation auto-save and CLI behavior during rollout.

## Review handoff

Implementation was subsequently requested by the user. The three slice plans and
`docs/obsidian-brains.md` record delivery and operational requirements. No live
publication, push or deployment is authorized by this document. The user separately
authorized the local commit and rebase/merge to `main`.
