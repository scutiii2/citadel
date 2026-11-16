# Cleanup: chat_app importer and `/shares/revoke`

Branch `chore/retire-importer`. Approved by the owner on 2026-11-16.

## Removed
- Portcullis: `services/chat_app_import.py`, `scripts/import_chat_app.py`, `tests/test_import_chat_app.py`, the README section "Moving from chat_app", and its entries in the layout lists and the `root-project-scaffold` skill.
- Stronghold: `POST /shares/revoke` (Portcullis no longer calls it; deleting a chat revokes its links in the same call), `RevokeBody`, and its three tests. Portcullis's fake upstream no longer answers it.

## Checked
`apps/legion_admin` `vue-tsc --noEmit` is clean: the old `ConnectionsView.vue` error is gone.
