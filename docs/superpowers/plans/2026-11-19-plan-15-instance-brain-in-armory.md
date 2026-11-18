# Plan 15 — Instance Brain in Armory

Base: `main` at `c76a4c2e`. Move the shared vault connection to Armory Admin, alongside Connections.

## Interfaces

| Consumer | Current interface and responsibility | After cutover |
| --- | --- | --- |
| Portcullis `routes/brains.py` | Authenticates the browser and proxies to Stronghold. Stronghold stores encrypted records and immutable revisions in db_gateway. | Personal settings, browsing, destinations and promotions retain their public contracts. New `/api/admin/brain` settings proxy gates on `settings.manage` and signs fixed requests to Armory `/admin/brain`. |
| Portcullis `routes/chats.py`, `routes/server_info.py`, `services/second_brain.py` | Chat preferences, turn availability and server-info availability check `/brains/writable/{scope}` and Armory's Obsidian write tool. | Keep those callers. Stronghold obtains the shared destination metadata and writability from Armory without credentials. |
| Portcullis `services/permissions.py` | `settings.manage` manages the instance connection. `brain.instance.publish` enables shared writes. | Keep both permissions. Portcullis checks staff access before proxying to Armory. Armory revalidates the management permission through Stronghold, which asks Portcullis for current account permissions before settings or vault access. Signed-in accounts can read. Writes additionally require the vault write switch. |
| Stronghold `brains/routes.py`, `brains/promotions.py` | Own personal settings, account purge, Note publication, receipts and suggestions. Bind each publication to a vault revision and generation. Forward deterministic operations to Armory. | Keep personal connections in Stronghold because they are owner-scoped and deleted with the account. Stronghold uses a signed metadata route for shared destinations, and Armory resolves shared credentials locally. Personal resolution and existing publication IDs stay compatible. |
| Armory Obsidian resolver, operation route and indexes | Resolve through Stronghold, perform vault I/O and lease indexes by revision generation. No managed record falls back to the legacy Obsidian configuration. | Armory stores the shared record in its settings database with an encrypted credential. `GET/PUT /admin/brain`, `POST /admin/brain/test`, `GET /admin/brain/status` and `POST /admin/brain/disable` manage it. Tests list the candidate vault root only. Saved status uses the committed record. Saving retires derived state for the old generation. Legacy fallback remains visible as “No managed API key.” |
| Legion `runtime/internal_auth.py`, Stronghold `agents/gateway.py` | Forward signed requester and the chat's selected Brain scope to Armory. | Keep scope forwarding and the resolver's restriction against switching an auto-save destination. |
| Ember Brains, Notes and chat | Brains edits the personal scope and browses either vault. Notes consumes destinations and revision-bound publications. Chat consumes availability. | Keep existing consumer paths and response shapes. |

### Migration and rollout

Stop every pre-Plan-15 Stronghold process before deploying the new Stronghold. Start the matching Armory build after Stronghold, followed by Portcullis and the admin apps. Armory attempts migration at startup and retries when the source is unavailable. Stronghold exposes only the existing shared record through an Armory-only signed migration call. The payload is sealed to an ephemeral Armory public key authenticated by its service identity. Preserve revision, generation, enabled state, folder, publishing flag and encrypted-at-rest credential. Distinguish a confirmed absent record from a failed fetch. A persisted migration marker prevents overwriting an Armory edit on restart. After the import commits, Armory sends a signed acknowledgement tied to the imported revision and generation. Stronghold deletes only those old shared settings and their revisions. Retry cleanup after a failed acknowledgement. Back up Armory's identity volume alongside its settings database.

## Verification

1. Write failing tests for migration, authorization, existing readers, key handling and candidate-only tests.
2. Move Armory storage and routes, point Stronghold at Armory for shared destinations, and sync the signed caller policy.
3. Move the form to a Brain page in Armory Admin. Test that the stored key never populates the view. Remove the Portcullis Admin form and its client.
4. Run app suites from their directories. Compare the full background Portcullis run with the two known port-0 failures.
5. Search all admin apps and Portcullis for the removed Tool services card, routes, clients and tests.

## Changes found during work

- Stronghold owns the old instance record. Portcullis proxies it and checks eligibility. Migration therefore reads Stronghold's current committed revision.
- Obsidian's resolver lives under `src/capabilities/obsidian/utils/`.
- An omitted key is retained only at the same HTTPS origin. Test applies the same rule. Disable uses the saved revision and can disable the legacy connection.
- Legacy write availability reflects Armory's configured endpoint, credential presence and write flag. No managed key is exposed.
- Vault refusals are settings errors so a redirect cannot look like a successful test and a vault 401 cannot clear the admin's Citadel session.
- The old Portcullis Admin browser spec was retired. Its failed-save and key-presence assertions moved to Armory Admin's unit tests.
- The Tool services card and API are absent from the scanned code. Stronghold Admin's README was the only remaining reference and was corrected in Part 2.
