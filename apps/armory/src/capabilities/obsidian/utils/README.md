# obsidian/utils/

`gateway.py` owns the Local REST API HTTPS client and literal vault-path guard.
Its public operations are `list`, `search`, `read`, `write` and `append`.
Configuration is passed by `tool.py`; `domain.py` formats typed results.
`ObsidianGatewayError` exposes safe messages and an optional HTTP status,
without transport exception details or remote response bodies.

The reusable gateway and path guard are catalog-tagged. No runtime state is stored here.

`chunking.py` preserves Markdown heading trails and metadata. `embeddings.py`
defines the local embedder boundary and Ollama implementation. `index_store.py`
defines the store boundary with SQLite FTS5/sqlite-vec persistence. `index.py`
owns incremental scanning and hybrid ranking. The process-owned periodic worker
lives in `src/capabilities/obsidian/utils/obsidian_index.py` so capability reloads do not duplicate it.
