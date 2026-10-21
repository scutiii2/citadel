# Obsidian brains and Notes promotion

Memory holds short account facts and preferences. Notes remain account-owned
captures and drafts. The Instance Brain is shared durable knowledge, readable by
every valid signed-in account. Each account can optionally connect a Personal
Brain that other product accounts cannot access. Promotion preserves the Note;
it creates a separate Markdown document, without automatic synchronization.

## Connect a vault

In Ember Admin, open **Workspace settings → Instance Brain**. Managing the shared
connection requires `settings.manage` and the existing staff verification rules.
In Ember Web, open **Settings → Personal Brain** to configure your own connection.
Use the Obsidian Local REST API plugin's HTTPS endpoint and API key. The endpoint
must be reachable from Armory, not just from the browser or the user's desktop.

Test connection performs read-only probes against the draft. Save explicitly
activates the revision. Leaving the API-key input empty preserves the saved key;
read responses show only whether a key is configured. Disable immediately prevents
new resolutions and retires derived indexes. Check saved status reports connection
and index state. Failed saves retain the editor's draft.

Personal endpoints allow private LAN addresses but refuse backend loopback,
link-local, metadata, unspecified, multicast and reserved targets. Each HTTPS
connection uses checked DNS addresses directly, keeps the original hostname for
TLS verification, refuses redirects, and ignores proxy environment variables.
Install the plugin certificate in the backend trust store when necessary; there
is no personal TLS bypass. An instance administrator can configure a local vault.

API keys are encrypted by Ember API's existing SecretBox in db_gateway. Protect
the existing encryption key together with storage backups. Product account
isolation does not hide data from the operator of the deployment.

## Backend configuration and compatibility

Armory needs `EMBER_API_URL` to reach Ember API's internal connection resolver.
The local default is `http://127.0.0.1:8030`; Compose sets
`http://ember_api:8030`. Both services require the same `INTERNAL_API_TOKEN`.
Resolution fails closed without a token and trusted, valid account UID. No browser
or model supplies an owner UID or receives a stored credential.

Existing Obsidian environment settings remain the legacy Instance Brain until a
managed connection is saved. A managed disabled connection never falls back to
the environment. The legacy read-only mount remains supported; managed connections
use remote enumeration and do not reuse an unrelated mounted vault. Environment
changes still follow the deployment's restart rules; managed saves do not require
a process restart.

Promotion requires Local REST API **5.2.0 or newer** with the documented conditional
create contract. Citadel verifies the plugin version, then uses `If-None-Match: *`.
Older and unrecognized versions are refused for promotion. See the plugin's
[conditional-write specification](https://github.com/coddingtonbear/obsidian-local-rest-api/blob/main/docs/openapi.yaml).
Read-only connection tests never write a probe document.

Migration `0025` adds `brain.instance.publish` to Administrator only; other roles
receive no automatic grant. It also gives existing chats the explicit `instance`
destination. Shared MCP writes, append, manual promotion and auto-save require
publish permission and connection write enablement. Existing capability selection,
tool switches, tool execution permissions and approvals still govern agent use.
Dedicated brain browsing does not require a Supermarket opt-in.

## Browse and retrieve

Open **Brains** to browse/read a selected vault or search `instance`, `personal`,
or `both`. Results identify scope, connection label, path and heading, together
with refresh state. Combined search interleaves text ranks or fuses semantic ranks
per source; separate raw vector scores are not compared. An unavailable source is
reported alongside healthy results. Contradictory documents retain their citations.

Remote indexing checks up to 10,000 enumerated children and 32 folder levels, uses
the existing bounded REST responses, hashes Markdown, and refreshes incrementally.
Only a completed scan removes unseen documents. Partial scans retain completed
documents of the same generation. First search can report indexing with no results.
The registry allows eight generation runtimes, two concurrent refreshes and two
scoped embedding calls; idle runtimes retire after 15 minutes. Busy retirement can
ask the caller to retry rather than reopen a database being removed.

Every managed save starts a fresh generation, including credential rotation. This
conservative policy avoids reusing content under a changed authorization scope.
Obsolete workers cannot attach results to a replacement generation. Existing
dispatched operations may finish against their original snapshot.

## Promote Notes

Save a Note, then choose **Promote to Obsidian**. Review the destination, audience,
collision-resistant path, editable Markdown and rendered preview. A shared
publication explicitly requires acknowledging that every signed-in user can read
it. The backend rechecks Note ownership/content/revision, destination revision and
permission before dispatch.

The promotion is reserved in storage before a create-only remote write. Retries
and concurrent submissions converge on that reservation. A timeout preserves a
pending record; retry or **Reconcile publication** checks the reserved path by
content hash. Reconciliation can confirm a completed write after the original Note
was edited. A confirmed pre-write collision permits a new, atomically reserved
path; an unknown write outcome keeps its original path. Different remote content
is never overwritten. Later Note edits show that the source changed and can be
published explicitly as a new version. Shared documents contain no automatic
private source identifiers or promotion metadata.

**Suggest promotions** reviews eligible Notes whose agent-access switch is on.
**Ask AI about this Note** requires explicit consent to send the selected Note,
including a private Note, to the configured AI provider. Consent does not change
the persistent access switch. Review batches allow at most 20 Notes and 40,000
content characters; larger selections require smaller batches. Suggestions favor
durable decisions, reusable procedures, developed research and stable knowledge.

The interpretation path has no tools. Calls obey existing token limits and actual
usage is recorded even for invalid model output. IDs, destinations, paths, tags
and drafts are validated as untrusted output. Suggestions never publish. Accepting
one opens the same review used by manual promotion; dismissals are keyed to source
content and destination generation. Changed Notes or destinations invalidate old
suggestions. Personal is preferred when writable and configured.

Conversation auto-save has an explicit instance/personal destination. Existing
enabled chats remain on `instance`; a new Web opt-in chooses a destination. Loss
of access disables saving and produces a visible notice. Trusted turn metadata
prevents a model from changing the selected destination. There is no fallback to
another brain. CLI parsing and optional turn parameters preserve this contract.

## Stored and generated state

Ember API owns db_gateway collections `brain_connections`,
`brain_connection_revisions`, `brain_promotions`, `brain_promotion_attempts`,
`brain_promotion_decisions`, `brain_promotion_requests` and `brain_suggestions`.
Connection revisions and promotion decisions use create-if-absent claims; mutable
head records are recoverable hints. Personal records use immutable account UID.

Armory's derived indexes live beside `OBSIDIAN_INDEX_PATH`, under
`brains/<connection-generation-model hash>/index.db`, with SQLite WAL/SHM and an
`owner.json` cleanup manifest. This private generated state contains vault text;
persist and protect the parent directory deliberately. It is disposable and never
authoritative. Cleanup waits for active readers and workers before removing files.
Account deletion removes personal connections, encrypted credentials, suggestions,
promotion records and personal derived state. It never deletes remote documents or
previously published shared knowledge. Failed remote cleanup is logged; access is
already revoked by account deletion and subsequent resolver checks.

Implementation verification uses fake vaults, embeddings and model responses. A
live smoke test still needs a reachable configured vault, trusted certificate,
embedding service and configured interpretation agent. No live publication or
deployment is part of implementation verification.
