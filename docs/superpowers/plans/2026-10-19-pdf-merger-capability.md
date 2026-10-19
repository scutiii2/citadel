# Native PDF merger capability implementation

The user requested implementation of `PDFMerger/docs/codex-armory-capability-brief.md` in a separate worktree and branch. This records the implementation scope and verification; it adds no further approval gate.

1. Create isolated `codex/` branch and worktree. Keep the standalone PDFMerger source unchanged.
2. Port the pure converters, merge planner/assembler, store, signing and cooperative job queue into capability `utils/`; retain page selection, rotations, image layout, metadata and bookmarks.
3. Add three native tools: inspect and list with slash commands/read-only declarations, plus structured-plan MCP-only merge. Enforce stable account UID ownership and generic unavailable-file errors; fence user filenames as data.
4. Own mutable state in a shared runtime on one dedicated loop, surviving capability reload. Configure tuning and generated storage under `specifics/pdf_merger/`, cap MCP waits at 100 seconds and preserve cooperative cleanup.
5. Route existing Ember PDF uploads to native storage and add signed browser download delivery. Preserve internal-token checks, UID propagation and the existing 15 MiB HTTP cap. Leave standalone IDs and extension configuration unmigrated.
6. Document setup, extension deduplication, settings, bearer-link expiry, storage lifecycle and operator restart requirements. Add example tuning only.
7. Verify ported engine tests, native ownership/auth/download/runtime tests, shared upload/identity regressions, capability shape and tool declarations. Review the final diff and report the worktree/branch and remaining deployment actions.

Ported engine verification: 116 tests passed using the isolated `.venv_pdf` runtime. Windows asyncio requires local socket pairs, which the execution sandbox blocks, so runtime test runs use approved escalation.
