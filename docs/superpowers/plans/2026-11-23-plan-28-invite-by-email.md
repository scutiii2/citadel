# Plan 28: Invite by email only, verified at registration, Armory email health check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Run the four tasks straight through in the current checkout and report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** (1) An invite needs an email address and is delivered only by email; the admin page never shows the code. (2) The person who registers with that emailed code is verified automatically. (3) An unverified account can reach only the verify screen (and logout / account), never chat, and the "verification is optional" switch is removed. (4) Armory's email capability gets a health check; the Invite member button uses it to say whether email can be sent.

**Architecture:** The invite code travels only inside the email, so holding it proves the mailbox. Registration therefore requires the registering email to equal the invite's email, and then sets `email_verified = True`. Portcullis asks Armory (`tool_email_checkHealth`, read-only, no mail sent) before it creates an invite, and exposes the answer on a status route that the Invite member drawer reads. An invite whose email fails to send is deleted, so no code exists that nobody can see.

**Tech Stack:** Python (Armory, Portcullis, FastAPI, SQLAlchemy), Vue 3 + TypeScript (`portcullis_admin`, `ember`), pytest, vitest.

## Global Constraints

- Work in the current checkout and branch. No branch, worktree, commit or push unless the user asks.
- Tests per task: only the files named, run once. Python from the app folder: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` (fallback: the app's `.venv\Scripts\python.exe -u -m pytest ...`). Web apps: `pnpm exec vitest run <files>` then `pnpm exec vue-tsc -b`. No full suites, no Docker, no baseline run. A run over about 2 minutes: stop and say so.
- Keep `apps/ember_web` untouched (reference only). Never read, print or write `.env*`, `secrets/`, key files. Never open a real `settings.db`. No reduced-motion code. Use `uv` and `pnpm`. Keep line endings. Edit with editor tools.
- Guards fail closed: if the health check cannot decide (Armory down, timeout, error), the answer is "not ready". Health reasons are fixed texts and never include an exception message, host name, user name or password.
- The code is never returned by any API, never logged, never stored in clear (only its SHA-256, as today).
- Existing database: no migration. `InviteCode.delivery_method` stays and is always written as `"email"`. No open invites exist anywhere, so there is no legacy-invite path: every invite has an email.
- Admin-app rule: `portcullis_admin` and `ember` do not share code. Change each app on its own.

## Decisions (already made)

| Question | Decision |
|---|---|
| Registering with another email than the invite's | Refused, 409 "This invite was sent to a different email address". |
| Email fails to send when creating | Invite row deleted, 503 with the fixed delivery error. Admin retries. |
| Email not ready when creating | 503 with the health reason, before any row is created. |
| "Accounts must verify their email" switch | Removed everywhere. Verification is always required. |
| Unverified user with no code | The verify screen lets the user request a code themselves ("Email me a code") through the existing `POST /api/auth/verify-email/resend` (30 s cooldown, 5 per hour). It never claims a code was already sent. |
| Verification still needed for | A changed email address (existing behavior). The verify screen, resend and admin "send verification" stay. Registration never sends a verification email. |

## File map

- Armory: `apps/armory/src/services/email/send.py` (extract connection), `apps/armory/src/services/email/health.py` (new), `apps/armory/src/capabilities/email/{contract,domain,tool}.py`, `.../email/README.md`, `.../email/help.json` if tools are listed there, test `apps/armory/tests/test_email_capability.py` (+ new `apps/armory/tests/test_email_health.py`).
- Portcullis: `src/services/email_service.py`, `src/services/email_templates/invite.txt`, `src/services/otp_service.py`, `src/services/registration_service.py`, `src/routes/admin.py`, `src/routes/auth.py`, `src/deps.py`, `src/config.py`, `src/services/app_policy.py`, `src/services/config_validation.py`, `src/routes/internal.py`, `src/routes/attachments.py`, `README.md`, `configs/README.md`; tests `tests/test_registration.py`, `tests/test_admin.py`, `tests/test_email_service.py`, `tests/test_optional_verification.py` (delete), `tests/test_staff_verification.py`, `tests/test_app_policy.py`, `tests/conftest.py`.
- portcullis_admin: `src/api/AdminClient.ts`, `src/components/admin/InvitesPanel.vue` (+ test), `src/views/InvitesAdminView.vue`, `src/views/OverviewView.vue` and `src/components/AdminNav.test.ts` only if they hold the old button text, `src/components/AppConfigCard.vue` (+ test), `src/api/AppConfigClient.ts`, `src/stores/auth.ts`, `src/api/AuthClient.ts`, e2e files that click "Create invite".
- ember: `src/api/auth/AuthClient.ts`, `src/stores/auth.ts`, `src/features/auth/views/RegisterView.vue`, `src/features/auth/views/VerifyEmailView.vue`, `src/features/account/AccountView.vue`, tests beside them.

---

### Task 1: Armory email health check

**Interfaces:**
- Produces: MCP tool `tool_email_checkHealth() -> HealthResult` with `HealthResult(ready: bool, message: str)`. Hidden from chat (`meta={"hidden": True, ...}`), `readOnlyHint=True`, `@offload`, no slash command. Same registration style as `tool_email_getAuditLog` in `tool.py`.
- Produces: `services/email/health.py::check_email_health(config_path: Path | None = None) -> tuple[bool, str]`.

**Behavior of `check_email_health`, in this order, first failure wins (reason texts are exact):**
1. Capability switch off (`capability_registry.is_enabled("email")` false or `KeyError`): `(False, "The Email capability is switched off in Armory.")`
2. No email document (`email_document(path) is None`): `(False, "Email is not set up. Fill in the Email page of Armory Admin.")`
3. `load_email_config` raises, or `security` not in `ssl | starttls | none`: `(False, "The email settings are invalid. Check the Email page of Armory Admin.")`
4. Open the SMTP connection the same way a send does (greeting, STARTTLS if set, login if a password is set), then close it. No MAIL FROM, no message. Any exception: `(False, "Armory could not log in to the mail server. Check the Email page of Armory Admin.")`
5. Otherwise `(True, "Email is ready.")`

- [ ] **Step 1: Refactor.** In `send.py` pull the connection block (SSL vs plain client, `starttls`, `login`) into one context manager `open_smtp(config)` that yields the logged-in client. `send_email` uses it and behaves exactly as before (same timeout 15, same order, same security-mode check before any socket). Run `tests/test_email_capability.py` and the existing send tests once to prove nothing changed.
- [ ] **Step 2: Failing tests** in `tests/test_email_health.py`, with `smtplib` replaced by fakes: each of the five outcomes above; step 4 failure when `login` raises (assert the returned text does not contain the exception text or the password); health never calls `sendmail`; password-less config does not call `login`. Run, see them fail.
- [ ] **Step 3: Implement** `health.py`, `HealthResult` in `contract.py`, `EmailDesk.health()` in `domain.py`, the tool in `tool.py`. The tool returns `HealthResult(ready=..., message=...)`; it never raises for a "not ready" answer.
- [ ] **Step 4:** Add the tool to `README.md` (tools table, row "MCP-only, no mail sent, used by Portcullis before an invite") and to `help.json` if that file lists the audit tool. Run `tests/test_email_health.py` and `tests/test_email_capability.py` once.

---

### Task 2: Portcullis — invite by email, auto-verify, always-required verification

**Interfaces:**
- Consumes: `tool_email_checkHealth` from Task 1 (returns `ready`, `message` in `structuredContent`).
- Produces: `EmailHealth(ready: bool, reason: str)` dataclass and `EmailSender.health() -> EmailHealth`; `OtpService.discard_invite(invite: InviteCode) -> None`; `GET /api/admin/invites/email-status -> {"ready": bool, "reason": str | null}`; `POST /api/admin/invites` body `{"invitee_email": EmailStr}` returns 201 `InviteOut` (no code, no `email_sent`).

- [ ] **Step 1: Failing tests first.**
  - `test_registration.py`: invite with email, register with the same email in other letter case: account created, `email_verified` is True, no verification code row, no verification email sent. Different email: 409 "This invite was sent to a different email address", invite stays unused. Update the existing registration tests that create invites without an email so they create one with an email and register with it.
  - `test_admin.py`: create without `invitee_email`: 422. Create with email: 201, body has no `code`; the fake email sender received the code once. Health not ready: 503 with the reason, no invite row. Send fails (`EmailDeliveryError`): 503, no invite row left. `GET /invites/email-status` returns ready and not-ready answers, and `{ready: false}` with a fixed reason when `health()` raises. Permission: needs `invites.manage`.
  - `test_email_service.py`: `health()` returns the tool's answer; an exception or a non-`False` `isError` gives `(False, "Armory could not be reached. Check that Armory is running and Portcullis can call it.")`.
  - `test_staff_verification.py` / replace `test_optional_verification.py`: an unverified account is refused (403 "Email not verified") by a permission-gated route and by `internal._is_usable`, with no setting able to turn that off. Delete `test_optional_verification.py`.
- [ ] **Step 2: Email sender.** In `email_service.py` add the `EmailHealth` dataclass, add `health()` to the `EmailSender` protocol and `McpEmailSender` (same `mcp_session`, tool `tool_email_checkHealth`, no arguments; catch every exception and return the fixed text above, never the exception text). Factor the shared "call a tool" lines out of `_send` only if it keeps `_send` byte-for-byte equal in behavior. Update every fake `EmailSender` in `tests/conftest.py` and in tests (a `health` returning ready by default, settable per test).
- [ ] **Step 3: Template.** `invite.txt` becomes:

```
You've been invited to Ember.

1. Open Ember and choose "Create an account".
2. Enter this invite code: $code
3. Use this email address for your account: $email

The code works once and expires at $expires_at UTC. Do not share it.
```

  `send_invite` passes `email=to` to `render_template`.
- [ ] **Step 4: Invites.** `otp_service.py`: `create_invite` unchanged in signature but `delivery_method` is passed `"email"`; add `discard_invite`. `admin.py`: `CreateInviteRequest` has only `invitee_email: EmailStr` (required); remove `delivery_method`, `CreatedInviteOut`, `email_sent`, `email_error`. Order in `create_invite`: delegation check (as today), then health (503 with `reason` if not ready), then create row, send, on `EmailDeliveryError` discard the row and 503. Log line stays `Created invite #id for <email>` and never contains the code. Add the status route before the `/invites/{invite_id}` routes.
- [ ] **Step 5: Registration.** `RegistrationService.register`: after the invite is found, if `invite.invitee_email` is None or `email.lower() != invite.invitee_email.lower()`, raise `RegistrationError("This invite was sent to a different email address")` (a None email fails closed). Build the `Account` with `email_verified=True`. `auth.py` `register`: send no verification email; `RegisterOut` becomes just `account` (remove `verification_email_sent` and `email_error`, and the `send_verification_code` call there; the helper stays for resend). Remove the `require_email_verification` branch.
- [ ] **Step 6: Remove the switch.** Delete `require_email_verification` from `config.py` (field and loader), `app_policy.py` (`KEYS`, view, validator), `config_validation.py`, and `AccountOut.email_verification_required` in `auth.py`. In `deps.py`, `attachments.py` and `internal.py` make the unverified check unconditional. Add no code or test that tolerates the old key: it is stale data. Remove it from every tracked config and doc (`configs/config_app.json` does not hold it today; confirm), from `README.md` and `configs/README.md`, and from `apps/ember_web/SMOKE_TEST.md` only if that is the one allowed doc edit (otherwise list it under Findings). `grep -rn "require_email_verification" apps/portcullis apps/portcullis_admin apps/ember .agents` must find nothing (the `ember-feature-scaffold` skill text counts: edit it). Do not touch any `settings.db`.
  Add one test in `test_auth.py` or `test_staff_verification.py`: an unverified, logged-in account can call `POST /api/auth/verify-email/resend` (200, a code is created, the fake sender gets it) and then `POST /api/auth/verify-email` with that code (verified), while a permission-gated route still answers 403 before the code is entered. A second resend inside 30 s answers 429.
- [ ] **Step 7: Run once:** `tests/test_registration.py tests/test_admin.py tests/test_email_service.py tests/test_staff_verification.py tests/test_app_policy.py tests/test_auth.py` from `apps/portcullis`.

---

### Task 3: portcullis_admin — Invite member

**Interfaces:**
- Consumes: Task 2 routes. `adminClient.createInvite(email: string): Promise<Invite>`; `adminClient.inviteEmailStatus(): Promise<{ ready: boolean; reason: string | null }>`. Remove the `CreatedInvite` type and the `delivery_method` argument.

- [ ] **Step 1: Failing tests** in `InvitesPanel.test.ts` (rewrite the cases that used the code, the toggle and the copy button):
  - The opener and the drawer title read "Invite member" (grep every "Create invite" / "Create an invite" in `src` and `e2e` and change it).
  - Opening the drawer calls `inviteEmailStatus` once. Ready: the submit button is enabled once a valid email is typed. Not ready: the reason is shown, the submit button is disabled, and a "Check again" button calls the status again and re-enables on ready.
  - The email field is required; with it empty the submit button is disabled.
  - After success the drawer shows "Invitation sent to <email>." and no code, no copy button, no "shown only once" notice appear; the open-invites list reloads and `changed` is emitted.
  - A 503 from create shows its message in the error line and keeps the form.
  - The open-invites table has no Delivery column.
- [ ] **Step 2: Implement** in `InvitesPanel.vue`: delete `byEmail`, the watch, the toggle, `CopyButton`, the `created.code` block and the "appears only once" notice. Add `emailStatus` (`checking | ready | blocked` with `reason`), loaded in `openCreate` and by "Check again". Email input: `required`, label "Email of the new member", no "(optional)". Primary button text "Send invite" (busy "Sending ..."). Heading `<h3>`: "Invite member"; muted text: "We email a one-time code. It works for 7 days. The person must register with this email address." Use the existing `.error`, `.muted` and button styles; add no new color or radius.
- [ ] **Step 3: Remove the switch.** `AppConfigCard.vue` (type, `toForm`, diff line, checkbox), `AppConfigClient.ts`, its test. In `stores/auth.ts` `needsVerification` is `account !== null && !account.email_verified`; drop `email_verification_required` from `AuthClient.ts`.
- [ ] **Step 4: Run once:** `pnpm exec vitest run src/components/admin/InvitesPanel.test.ts src/components/AppConfigCard.test.ts src/views/AdminView.test.ts src/components/AdminNav.test.ts src/router/index.test.ts` then `pnpm exec vue-tsc -b`. Update the e2e specs and fake APIs that created invites by code (`e2e/personal.spec.ts`, `e2e/workspace.spec.ts`, `e2e/workspaceFakeApi.ts`, `e2e/fakeApi.ts`); do not run e2e unless asked.

---

### Task 4: ember — registration and the verify trap

- [ ] **Step 1: Failing tests.** (a) Store: `needsVerification` is true for any account with `email_verified` false, with no other flag. (b) `RegisterView`: after a successful register the router goes to `chat` (the account is verified); remove the `unsent` query handling and `verification_email_sent` from `AuthClient.ts` and `VerifyEmailView.vue`. The page tells the user to use the address the invite was sent to. (c) Router: an unverified account asking for `/` or any chat route is redirected to `verify-email`; a page marked `anyAccount` stays reachable; a verified account on `verify-email` is sent home. Confirm which routes carry `meta.anyAccount` and that chat and tools are not among them.
  (d) `VerifyEmailView`: it no longer says a code was sent. Subtitle: "Confirm {email} to use Ember." The first action is a primary button "Email me a code" that calls `resendVerification` and then shows "A code was sent to {email}. It expires in 15 minutes."; the code field and "Verify" stay visible all the time (a user may already hold a code); "Send a new code" in the footer becomes the same button's later label. A 429 shows its "Try again in N s" message; a 503 shows its message. No `unsent` query handling.
- [ ] **Step 2: Implement.** `stores/auth.ts` as in Task 3. `AuthClient.ts`: drop `email_verification_required` (test file too). `RegisterView.vue`: replace the verify redirect with `router.replace({ name: "chat" })`; subtitle "Registration needs an invite code sent to your email."; under the email field a muted line "Use the email address the invite was sent to." `AccountView.vue`: remove the optional-verification wording and branches; the banner for an unverified account says the email must be verified to use Ember.
- [ ] **Step 3: Run once:** `pnpm exec vitest run src/stores src/features/auth src/features/account src/router` then `pnpm exec vue-tsc -b`.

---

## Out of scope

Resending or re-issuing an invite from the list, one open invite per email, rate limits on invite emails, an admin "mark verified" action, invite links instead of codes, changing the verify-code email, any `ember_web` change. A health check cache (each drawer open and each create runs one SMTP login; fine at this size).

## Risks to report

- Accounts that were unverified under the old optional setting land on the verify screen after this change and request a code themselves there. An admin can also use "Send verification".
- A user who changes their email, or an old unverified account, cannot verify while SMTP is down; the screen shows the delivery error.
- Live copies of `configs/config_app.json` (and any `app_config` row for `require_email_verification` in a real `settings.db`) are outside the repo. The owner removes the key there by hand; the code no longer reads it. Say so in the report.
- Never run the health tool or an invite against a real mail server in tests; fakes only.

## Report

Per task: files changed, test commands with pass counts, commands not run, Findings (anything the plan got wrong about the real code), and vault notes needing an update (`portcullis`, `portcullis_admin`, `armory`, `ember`, the roadmap row for Plan 28). Do not edit the vault.
