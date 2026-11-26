# PDF merger storage

The capability owns no files. PDF and image files live in the shared store (see the Files capability's guidelines); merge scratch files go to the store's `_work/` folder and are removed after each merge. Jobs, progress events and quota reservations are process-local memory, not a persistent job database.

Caps and lifetimes belong in the `tuning` table of `settings.db`, edited on the Limits page of Armory Admin and explained in `docs/settings.md`. They are never a tracked file. Secrets belong in Armory's normal environment configuration, never in the capability directory or sidecars. Signed links are generated from file IDs and expiry timestamps and are not persisted.
