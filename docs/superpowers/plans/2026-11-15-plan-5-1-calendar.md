# Plan 5.1: Calendar moves to Stronghold

Branch: `refactor/stronghold-calendar`. First domain of Plan 5; it also builds the shared pieces the later domains reuse.

## Tasks

1. Stronghold: `src/calendar/` (`store`, `fetcher`, `expander`, `events`, `channels`, `scheduler`, `runtime`, `routes`, `settings`), moved from Portcullis with imports changed. Routes under `/calendar`, plus `DELETE /calendar/accounts/{uid}` (purge).
2. Stronghold shared pieces: `document_store.py` (Treasury client), `secret_box.py`, `keys.py` (generated `keys.json`), `platform.py` (Portcullis internal API client), `config.py`, app lifespan.
3. Portcullis: `/internal` routes (`routes/internal.py`).
4. Portcullis: `/api/calendar/{path}` passes the request on after the `calendar.use` check. Calendar services, scheduler, VAPID code and the `calendar` config block are removed.
5. Treasury: connection `stronghold` (`data/stronghold.db`) and instance `stronghold`.
6. Compose: Stronghold gets `DB_GATEWAY_URL`, `PORTCULLIS_URL`, `STRONGHOLD_DATA_DIR=/data`, volume `stronghold_data`, config file `docker/configs/stronghold/app.json`.

## Accepted behavior changes

1. Calendar data starts empty: it is stored under Stronghold's own Treasury instance. Feeds, alarm rules and push subscriptions must be entered again (no migration, as decided).
2. The key that encrypts feed links and the web push key pair are new, kept in `stronghold_data:/data/keys.json`. `EMBER_VAPID_PRIVATE_KEY` and `EMBER_VAPID_PUBLIC_KEY` in Portcullis's `.env` are no longer read. Back the volume up: without the file, saved links cannot be read.
3. The `calendar` block moves from Portcullis's `config_app.json` to Stronghold's (`docker/configs/stronghold/app.json`). A `calendar` block left in Portcullis's file is ignored.
4. The Config issues page no longer warns that web push needs HTTPS: Portcullis does not know whether the calendar is on.
5. An email alert asks Portcullis to send it. When Portcullis is down, the alert is marked failed, as an SMTP failure was before.
6. Each scheduler tick asks Portcullis once for the switches and once per account with rules for the recipient. With many accounts this is many small calls every 30 seconds.
7. A calendar error in the Errors log has source `stronghold.calendar` (was `calendar`).
8. Stronghold being down makes `/api/calendar/...` answer 502 `Stronghold is unavailable`.

## Execution notes (2026-11-15)

- Executed in full. Stronghold suite: 67 passed (the moved calendar tests, plus keys, platform client and the skeleton's). Portcullis: new `test_internal_api.py`, rewritten `test_calendar_routes.py` and `test_calendar_config.py`; the full-suite result is in the commit message.
- Real local check: Treasury on test port 29902 and Stronghold on 29901. Default alarm rule, add feed, save timezone, push key, purge and an empty list afterwards all answered correctly; `keys.json` was created. Both servers stopped afterwards.
- Not run: Docker builds, Stronghold calling a real Portcullis (`/internal` is covered by tests on each side only), a real email or web push alert, the Calendar page in a browser.
- Removed from Portcullis with the code: dependencies `icalendar`, `recurring-ical-events`, `pywebpush`; `tests/test_vapid.py`.
- `/api/calendar/accounts/...` answers 404 in Portcullis: Stronghold's purge route is reachable only through the account delete.
