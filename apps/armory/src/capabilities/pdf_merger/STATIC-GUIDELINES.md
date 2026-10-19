# PDF merger storage

The capability owns generated state under `apps/armory/specifics/pdf_merger/.data/store/` by default, configurable through `MCP_PDF_MERGER_STORE_DIR`. The existing `specifics/*/.data/` ignore rule keeps it out of git. No cache or capability-specific log directory is created; standard Armory logging handles diagnostics.

| Location | Format and contents | Lifecycle |
| --- | --- | --- |
| `<store>/<sha256(owner)[:32]>/f_<32 hex characters>` | Original uploaded bytes or generated PDF bytes. Names supplied by users are metadata, never filesystem paths. | Generated and untracked; deleted on expiry sweeping or internal deletion. Default file lifetime is 6 hours. |
| `<store>/<owner hash>/f_<id>.json` | UTF-8 JSON `StoredFile` sidecar: file ID, owner session, original/safe name, MIME, kind, pages, size, creation and expiry timestamps. | Generated and untracked; rebuilds the in-memory index after restart and is removed with its file. |
| `<store>/<owner hash>/f_<id>.part` | Incomplete streamed upload or merge output. | Temporary; removed on validation failure or cancellation and reconciled after a crash during index loading. |
| `<store>/_work/<temporary directory>/` | Intermediate image-to-PDF conversions for one merge. | Temporary; removed after merge success, failure or cooperative cancellation. Startup removes empty abandoned work directories. |

Files and sidecars survive process restart until their expiry. Jobs, progress events and quota reservations are process-local memory, not a persistent job database. Index loading also removes orphan file bytes without a sidecar and stale partial files. Nonempty scratch directories left by an abrupt process termination are not automatically removed by startup; an operator may remove confirmed abandoned scratch data while Armory is stopped.

Tuning configuration belongs in `specifics/pdf_merger/configs/config_pdf_merger.json`; only its `.example` twin is tracked. It is hand-maintained configuration, never runtime data. Secrets belong in Armory's normal environment configuration, never in the capability directory or sidecars. Signed links are generated from file IDs and expiry timestamps and are not persisted.
