# Email runtime data

`.data/armory/email/audit.db` (Citadel folder) is a generated SQLite database of delivery
metadata, outside source and gitignored with `.data/`.
It is created on the first delivery attempt, retained across restarts, and
queried newest first with a maximum of 200 records per owner per request.
Records contain UTC time, owner, outcome, recipient count and Message-ID only.
No message bodies, addresses, subjects, codes or credentials belong here.
There is no static reference data or separate SMTP configuration in this folder.
