# Obsidian index state

`specifics/obsidian/.data/index.db` (configurable with `OBSIDIAN_INDEX_PATH`)
holds generated SQLite FTS5/sqlite-vec state: source hashes/mtimes, chunks,
vectors and metadata. SQLite may create adjacent `-wal` and `-shm` files.
These files are private generated state, gitignored by the existing specifics
rule. They contain vault text: protect them like the vault, not like source code.

The source is a separate read-only mount (`OBSIDIAN_VAULT_PATH`). The index
must be outside it. Indexing never writes to the mount. Missing documents are
removed after a complete scan. Failed refreshes retain completed notes and retry.
Stop Armory before manually removing index files; next search rebuilds them.
For a new embedding model choose a new index path and restart Armory.
No hand-maintained reference data or `static/` folder is used.

Managed remote brains additionally own `brains/<connection-generation-model hash>/`
beside the configured index path. Each directory contains `index.db`, its SQLite
`-wal`/`-shm` files, and `owner.json` (owner UID, connection ID and generation for
cleanup; no credential). All are private generated, disposable, gitignored state.
A managed save always creates a fresh generation; changing embedding identity
selects a new index. Idle/obsolete runtimes retire and removal waits for readers
and workers, including workers already awaiting retirement. Account deletion also
removes matching manifests/indexes left by earlier processes. No remote document
is deleted. Persist/protect the derived root deliberately in containers.
