# Plan 11: remove the calendar

Branch `refactor/remove-calendar`. The calendar belongs to its own project (`CalendarViewer`), not to Citadel.

## Removed
- Stronghold: `src/calendar/` (feeds, expander, alert scheduler, channels, `/calendar` routes), its tests, the `calendar` config block (code, example, docker config), the five `calendar_*` catalog collections, `icalendar`/`pywebpush`/`recurring-ical-events` dependencies, and the web push key pair in `keys.json` (old files still load; the extra fields are ignored). `PortcullisClient.recipient/switches/notify` went too.
- `utcnow` moved to `src/clock.py` (many modules took it from the calendar package).
- Portcullis: `routes/calendar.py`, `calendar.use` permission (stored role rows with the name are ignored), `calendar_inapp/email/push` settings, `/internal/accounts/{uid}/recipient`, `/internal/switches`, `/internal/accounts/{uid}/notify`, the config block, the calendar purge call, tests.
- `portcullis_admin`: `CalendarChannelsPanel` and its test, the three fields of `AppSettings`.
- Docs: READMEs, compose comment, vault notes.

## Left in place
Existing calendar documents in Treasury (`calendar_*` collections) and old `app_settings` rows stay unused; delete them by hand if wanted. `apps/ember` never had a calendar page.

## Not done
No live run. Portcullis suite and Stronghold suite pass; `portcullis_admin` vitest passes (197).
