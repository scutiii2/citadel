# capabilities/files/

Generic tools over Armory's shared file store (`src/services/user_files/`), which holds every upload and every file a
tool makes. Files belong to the signed-in account; the internal token never grants access to another account's files.

## Tools

| Tool | Purpose | Connection |
| --- | --- | --- |
| `tool_files_list` | List the account's unexpired files of every kind with fresh links. Read-only. | Local file store |
| `tool_files_inspect` | Details and fresh links for chosen file IDs, with per-ID failures. Read-only. | Local file store |
| `tool_files_view` | Return one owned image, or one page of an owned PDF (`page`, from 1), as MCP image content, long edge at most 1568 px; a PDF page is JPEG. Read-only. MCP-only and hidden from tool lists: Legion calls it to show a model an attachment. An owned WAV or MP3 file comes back as audio content. | Local file store |

## Slash commands

| Tool | Slash command | Parameters |
| --- | --- | --- |
| `tool_files_list` | `/files list` | No parameters. |
| `tool_files_inspect` | `/files inspect` | <ul><li>`file_ids` - required. Comma-separated IDs from chat uploads or the file list; at most 100 per call.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
| --- | --- | --- |
| 1 | *(manual - no tool)* | Upload a file through Ember chat. |
| 2 | `tool_files_list` | Find usable file IDs from the signed-in account. |
| 3 | `tool_files_inspect` | Check kind, size and expiry before using a file. |
| 4 | `tool_files_view` | Legion shows or plays an attached file to a model. |

## Enable

The capability ID is `files`. Restart Armory, refresh capabilities, and switch Files online. Uploads do not need this
capability: `POST /upload/file` is a core route. Switching the capability off removes these tools and image viewing.
