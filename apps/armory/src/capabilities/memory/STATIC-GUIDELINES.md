# capabilities/memory/ static and state files

## `.data/armory/memory/memory.db`

- Runtime state: a SQLite database created on the first save. Gitignored with `.data/`.
- Tables: `notes` (id, owner (the account uid), text, norm, created_at) and `notes_fts`, an FTS5 index over the note text whose rowid equals `notes.id`.
- Lifecycle: written by `tool_mem_save`, read by `tool_mem_search`, deleted from by `tool_mem_forget`. Never edited by hand; delete the file to wipe every user's notes.
- Contains user-stated personal facts. Back it up and protect it like account data. Note text is never written to the logs. Ember does store each answer's tool steps, including saved or searched note text, in the chat transcript, and `tool_mem_forget` removes the note from memory but not from past chats.
- Account identity comes only from a verified Portcullis requester token. Service assertions authenticate callers; missing identity refuses account operations.
