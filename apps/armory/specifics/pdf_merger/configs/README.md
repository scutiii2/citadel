# configs

`config_pdf_merger.json` is tracked; there is no `.example` twin. Its path can be changed with
`MCP_PDF_MERGER_CONFIG_PATH`. Restart Armory after editing.

| Key | Meaning |
|---|---|
| `file_ttl_hours` | How long an uploaded or merged file is kept. |
| `sweep_interval_minutes` | How often expired files are removed. |
| `download_link_minutes` | How long a signed download link works. |
| `mcp_wait_seconds` | How long a tool call waits for a merge before it answers "still running". |
| `limits.max_file_mb`, `limits.max_session_mb` | Size caps for one file and for one account's stored files. |
| `limits.max_segments`, `limits.max_output_pages`, `limits.max_image_megapixels` | Caps on one merge. |
| `limits.max_concurrent_merges`, `limits.job_timeout_seconds` | Parallel merges and the time one may take. |

The signing key and public address are in `../../../.env` (`PDF_MERGER_SIGNING_KEY`, `MCP_PDF_MERGER_PUBLIC_BASE_URL`).
Files are in `.data/armory/pdf_merger/store/` in the Citadel folder.
