# Calendar schedule and alerts — design

Date: 2026-10-24
Status: design approved in chat, awaiting written-spec review
Reference port: `D:\User\Documents\Programming\Python\CalendarViewer` (single-user Node app, ICS links and uploads, FullCalendar, no alerts)

## Goal

Each Ember account keeps a private, read-only schedule built from ICS links (for example Outlook/Office 365 published calendars) and gets alerts before events start. Alerts are rule based: each rule picks a channel and a lead time. A new account starts with one rule, in-app, 15 minutes.

## Scope

In scope:
- ICS links per account, fetched and parsed by the server.
- Read-only calendar page in ember_web (Day, Work week, Week, Month).
- Alarm rules with three channels: in-app, email, web push. Each channel has an admin switch and per-user rules.
- Admin and static configuration.
- A new permission, `calendar.use`.

Out of scope (decided):
- `.ics` file upload. Static snapshots go stale and would need server storage. Can be added later without changing the alert design.
- Sharing a schedule between accounts. Every schedule is private to its account.
- Per-feed alarm overrides. Rules are per account.
- The agent capability (see "Later step").

## Decision: everything lives in ember_api

Feeds, rules, the scheduler and the channels are ember_api services. Account, email address and push subscriptions already live there, so the scheduler needs no extra hop. Armory is not involved in v1.

Rejected: an armory capability like `pdf_merger`. Armory holds no accounts, email addresses or push subscriptions, so its scheduler would call back into ember_api and the data would live in two places.

## Backend (ember_api)

### Tables (one Alembic migration)

- `calendar_feeds`: `id`, `account_id`, `name`, `color`, `url_enc` (Fernet via `secret_box`, key `EMBER_SECRETS_KEY`), `enabled`, `etag`, `last_fetch_at`, `last_error`.
- `alarm_rules`: `id`, `account_id`, `channel` (`inapp` | `email` | `push`), `lead_minutes`, `enabled`.
- `push_subscriptions`: `id`, `account_id`, `endpoint` (unique), `p256dh`, `auth`, `created_at`.
- `calendar_alerts`: `id`, `account_id`, `rule_id`, `event_key` (uid + start UTC), `title`, `start_utc`, `channel`, `status` (`sent` | `failed`), `created_at`, `seen_at`. Unique on (`rule_id`, `event_key`): an alert fires at most once per rule and event.
- `calendar_prefs`: `account_id`, `timezone` (IANA name; the browser's zone is saved on first visit).

The default rule is created on first use of the calendar API, not in the migration.

### Services

- `calendar_service` — CRUD for feeds and rules and the event query. The only entry point for routes and for the later agent capability. Enforces limits and ownership.
- `calendar_fetcher` — https only (`webcal:` is rewritten to `https:`), blocks private and loopback addresses unless `allow_private_urls`, timeout, size cap, ETag / `If-None-Match`, no redirect to a blocked address.
- `calendar_expander` — turns ICS text into concrete events in a time range using `icalendar` and `recurring_ical_events`. Handles recurrence exceptions, drops `STATUS:CANCELLED`, treats floating times in the account's timezone, merges duplicates across feeds by uid + start + end.
- `alert_scheduler` — see below.
- `alert_channels` — a `Channel` protocol (`async send(alert, account) -> None`) with `InAppChannel`, `EmailChannel`, `PushChannel`. Adding a channel means adding a class.

### Alert scheduler

Started in the app lifespan, in the style of `BackupScheduler`. It never blocks the event loop: network and parsing run in the loop's async client or a worker thread.

1. Every `feed_refresh_minutes`, refresh each enabled feed of accounts that have at least one enabled rule, and keep the expanded events for the next `lookahead_hours` in memory. A failing feed records `last_error` and keeps its previous events.
2. Every `tick_seconds`, for each enabled rule whose channel is on in the admin config, find events with `start - lead <= now` and `now - (start - lead) <= late_grace_minutes`.
3. For each match, insert the `calendar_alerts` row first. If the unique key rejects it, the alert already fired and nothing else happens. Otherwise dispatch to the channel.
4. A channel error sets that row to `failed` and never stops other channels or accounts.
5. After downtime longer than the grace window, missed alerts are dropped, not sent in a burst.

Rules:
- Email is never retried, matching `email_service`.
- A push endpoint answering 404 or 410 has its subscription deleted.
- All-day events are skipped.
- Logs name the feed, never the URL or a token.

### Routes (`/api/calendar`, all need `calendar.use`, JSON only)

- `GET/POST /feeds`, `PATCH/DELETE /feeds/{id}`
- `GET /events?from=&to=` — expanded, merged, enabled feeds only
- `GET/POST /alarms`, `PATCH/DELETE /alarms/{id}`
- `PUT /prefs` (timezone)
- `POST /push/subscribe`, `DELETE /push/subscribe`, `GET /push/key` (public VAPID key)
- `GET /alerts?unseen=1`, `POST /alerts/{id}/seen`

The feed URL is accepted on create and never returned. `PATCH` may replace it. An account can only see its own rows; a foreign id returns 404.

## Configuration

### Admin (`app_settings`, edited in ember_admin Settings)

`calendar_channels` = `{inapp: bool, email: bool, push: bool}`. A rule on a disabled channel stays stored but is not dispatched, and the UI shows it as unavailable.

VAPID keys are generated into `.env` on first start, like `EMBER_SECRETS_KEY`. The Config issues page warns when:
- email is on but the armory `email` capability is offline;
- push is on but the site is not served over https (localhost excepted);
- the secrets key is missing, so stored feed URLs cannot be read.

### Static (`configs/config_app.json`, new `calendar` block)

| Key | Default |
| --- | --- |
| `enabled` | true |
| `tick_seconds` | 30 |
| `feed_refresh_minutes` | 10 |
| `lookahead_hours` | 48 |
| `late_grace_minutes` | 5 |
| `max_feeds_per_account` | 10 |
| `max_alarm_rules` | 10 |
| `max_ics_bytes` | 5242880 |
| `fetch_timeout_s` | 15 |
| `allow_private_urls` | false |

### Per user

Rules in `alarm_rules`, the saved timezone, and push subscriptions (one per browser). Email goes to the account's verified address. A push rule needs at least one subscription.

### Permission

`calendar.use`, held by Administrator. Existing roles keep what they have. Read-only access to alerts follows the same permission. The sidebar page can be hidden with the existing pages setting. No per-account capability toggle.

## Frontend

### ember_web, `features/calendar/`

Before building, read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system` (and `mobile-ui.md` for the narrow layout).

- Route `/calendar` gated by `calendar.use`, plus a nav entry.
- `@fullcalendar/vue3` with timegrid and daygrid. The browser receives already-expanded events, so there is no ical.js on the page.
- Ember tokens, accent and radius scale. The reference's Teams purple and green/gray status colors are not ported; finished events are dimmed.
- Feeds sidebar: add (label and URL), toggle, recolor, rename, remove with the project's confirm pattern.
- Alerts panel: list of rules (channel, lead time 5/10/15/30/60 or custom, enabled), add and remove. A rule whose channel is off shows why. Enabling push happens on a user click: permission prompt, service worker registration, `POST /push/subscribe`.
- Event dialog: a TS util ported from the reference with tests — description and Teams-footer split, Outlook safelink unwrap, http(s)-only links, Teams join button, dedupe source dots.
- `useAlertPoller` polls `GET /alerts?unseen=1` every 30 s and on tab focus, shows a toast and a browser `Notification` (pattern of `useCompletionNotify`), and marks alerts seen on dismiss.
- `public/sw.js` handles `push` and `notificationclick` (opens `/calendar`).

### ember_admin

Settings section with the three channel switches; Config issues warnings as above.

## Security and privacy

- Feed URLs are bearer secrets: encrypted at rest, never returned, never logged.
- SSRF guard on every fetch and on every redirect hop.
- Size and time caps on fetch; limits on feeds and rules per account.
- Ownership checks on every id; POST bodies must be JSON (existing rule).
- Push payloads carry the title and start time only.
- Deleting an account deletes its feeds, rules, subscriptions, alerts and prefs.

## Testing

- pytest: expander (recurrence, exceptions, cancelled, DST, floating times); scheduler with a fake clock (fires once, grace window, several rules, channel failure isolated, disabled channel); fetcher (SSRF, redirect, size, timeout, ETag); routes (permission, ownership, URL never returned); migration parity test; account deletion purge.
- vitest: event util, store, poller.
- Playwright against the fake API, light and dark, at 1280, 768 and 375 widths.
- Email and push use fake senders in tests. A live email and push smoke check is manual.

## Later step: agent capability

A thin armory capability (contract / domain / tool) lets the chat agent add or remove ICS feeds and set alarm types and lead times. It calls an internal ember_api route (internal token plus account `uid`) that calls the same `calendar_service`. Nothing in this design blocks it, and no data moves.

## Open items for the implementation plan

- HTTP client for the fetcher: reuse what `game_registry` uses if it supports the redirect-hop address check, otherwise `httpx`.
- `pywebpush` is blocking: run it in a worker thread.
- In-app alerts use polling in v1 (no SSE).
