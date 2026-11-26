# Files storage

This capability owns no state and no static data. The files belong to the shared store, under
`.data/armory/files/store/` by default, configurable through `MCP_FILES_STORE_DIR`.

| Location | Format and contents | Lifecycle |
| --- | --- | --- |
| `<store>/<sha256(owner)[:32]>/f_<32 hex characters>` | Uploaded bytes or bytes a tool generated. Names supplied by users are metadata, never filesystem paths. | Generated and untracked; deleted on expiry sweeping or deletion. Default lifetime is 1 hour. |
| `<store>/<owner hash>/f_<id>.json` | UTF-8 JSON `StoredFile` sidecar: file ID, owner account id, safe name, MIME, kind, pages, size, creation and expiry timestamps. | Rebuilds the in-memory index after restart and is removed with its file. |
| `<store>/<owner hash>/f_<id>.part` | Incomplete upload or generated output. | Removed on failure or cancellation and reconciled after a crash. |
| `<store>/_work/<temporary directory>/` | Scratch files of one PDF merge. | Removed after the merge. Startup removes empty abandoned folders. |

Caps and lifetimes are the `files` document in the `tuning` table of `settings.db`, edited on the Limits page of Armory
Admin and explained in `docs/settings.md`. The link signing key is `PDF_MERGER_SIGNING_KEY` and the public address is
`MCP_PDF_MERGER_PUBLIC_BASE_URL`.
