# Live-stack runbook (Plans 20e to 26)

One ordered list of every manual check that the plans left pending, plus checks for the later removals (22c, 22d, 22e). Nothing here has run against a live stack: the build tested with unit tests and mocks only. Run it top to bottom. If a step fails, stop and note the step number; later steps depend on earlier ones.

Tick each box and write the date and a few words next to a failure. Source plans are named in brackets.

## 0. Prepare (10 minutes)

- [ ] This is a fresh install: start with empty data folders (no old database, no old `settings.db`). No backup or migration of old data is needed.
- [ ] `git log --oneline -3` on `main` shows `dbe61f22` or later. Rebuild every image from `main`.
- [ ] Have three accounts ready: an administrator, a normal member (A) and a second member (B). Give one delegated admin only `tool_services.manage`.
- [ ] Do the user steps first: remove `OBSIDIAN_*` and `MCP_VAULT_DIR` from `apps/armory/.env.example` line 6 and your local `.env`.

## 1. Start rule and compose [Plans 23, 25]

- [ ] `docker compose up -d --build` with the setup overlay builds both gateways from their repos; `docker compose ps` shows both healthy. [23]
- [ ] After a restart without the overlay, `docker compose port conversation-gateway 29407` and `docker compose port decision-gateway 29406` print nothing, and `http://127.0.0.1:29407/health` does not answer from the host. [23]
- [ ] `docker compose exec legion python -c "import urllib.request; print(urllib.request.urlopen('http://conversation-gateway:29407/health').status)"` prints 200. The same call from `armory`, `stronghold` and `portcullis` fails to resolve the name. [23]
- [ ] With only the `legion` token created, a request to `http://conversation-gateway:29407/api/gateways` from Legion's container answers 401 without the token and 200 with it. [23]
- [ ] A key stored as `env:ANTHROPIC_API_KEY` works for a real chat turn in Ember; the admin page shows the key as present but never prints it; removing the variable from `.env.gateways` and recreating the container turns the entry to "no key". [23]
- [ ] `docker compose exec armory sh -c "env | grep -i API_KEY"` shows none of the gateway provider keys. [23]
- [ ] A standalone gateway stack for another project still starts with its own host port and data. [23]
- [ ] Laya through DecisionGateway still answers (Triage Assistant, ticket tagging) after saving `http://decision-gateway:29406` and its token in Legion. [23]
- [ ] Stop Treasury, start the rest. Each service stays up, `/health` answers, `/ready` shows Treasury `unreachable`. [25]
- [ ] With Treasury stopped, ask an agent to list tickets: the tool answers `[1002] DEP_UNAVAILABLE treasury unavailable` and the agent does not loop. Start Treasury again. [25]
- [ ] Break the service token for one call path: the answer is `[1004]` and the same call is not repeated in that turn. Restore it. [25]
- [ ] `GET /api/admin/ready` works as an administrator and answers 403 as a member. [25]
- [ ] Remove a service's registration in Treasury; within about a minute discovery registers it again, and a pinned name stays as pinned. [25]

## 2. Migrations and the permission rename [Plans 22b, 22e]

- [ ] Start Portcullis on an empty database: it logs "created" and reaches revision `0030` with no error (every migration runs from scratch). [22b, 22e, 27]
- [ ] Roles page lists `tool_services.manage` ("Manage tool services") and no `extensions.manage`; every role that held the old permission still holds the new one (check Administrator, Operator, Tool Services Manager). [22e]
- [ ] The starter roles are listed with the new names: `Tool Services Manager` (text "Member access plus tool services management.") and no `Power User`; `Operator` text says "tool services". [22e, 27]
- [ ] Log in as the delegated admin with only `tool_services.manage`: Ember shows the admin link, Stronghold Admin shows Tool services, and the Bard, Scribe and Reader forms save and test. [22e]
- [ ] Armory Admin with an account that has neither `capabilities.manage` nor another admin permission shows the no-access page naming only `capabilities.manage`. [22e]

## 3. Removed features are really gone [Plans 20j, 22, 22b, 22c, 22d]

- [ ] Ember: nav has no Memory, Brains or shared-extension entries. `/memory` shows the not-found or default page, not an error. Notes, Skills, Shares, Global and the memory control still open. A saved sidebar order that named Memory loads without error. [20j, 22b]
- [ ] Chat settings menu has no second-brain controls and no "Extensions:" line. Create, rename and pin a chat: nothing mentions a second brain. [22b, 22c]
- [ ] Ember's Capabilities page shows only private extensions; add and remove one of your own. [22c]
- [ ] `GET /api/notes`, `GET /api/memory`, `GET /api/extensions` and `GET /api/admin/connections` (signed in) all answer 404 or the unknown-route answer. `GET /api/connection-status` still answers. [20j, 22c]
- [ ] Armory Admin: no Connections page (`/connections` and `/extensions` go to the default page), no Brain page, Settings has no Obsidian section, Capabilities lists none of `obsidian`, `vault`, memory, notes or skills. [22, 22b, 22c]
- [ ] Ask an agent to use `tool_mem_search`: it does not exist. Ask it to save and recall a Brain note: it works. [22]
- [ ] A normal chat turn and an agent turn with tools still run end to end (Legion no longer takes `enabled_extensions`). A tool call from the agent runs under your account and a forced dependency failure shows a numbered error. [22c, 22d]
- [ ] Delete a test account that had notes, an old memory and Brain files: the purges run, the log has no `notes`, `brains`, `admin.notes_purge` or `admin.memory_purge` error, and the Brain files are gone. [20j, 22, 22b]
- [ ] Make a PDF merge in Ember: the download card shows "Expires in 60 min" or close, and later "Expired". Bard or Scribe dictation in Ember still works through Stronghold. [22]

## 4. Tickets and usage [Plan 21]

- [ ] File a ticket on Ember's Tickets page: it appears in the list and in staff's ticket admin; a staff reply makes it unread for the reporter.
- [ ] Ask the Ember agent to report a bug: it calls `stronghold__tool_ticket_createTicket`, tells the ticket id, and the ticket shows on the Tickets page.
- [ ] With the Triage Assistant running, two similar reports are grouped and tagged; with it stopped, a ticket is still filed, ungrouped.
- [ ] A forced tool failure files one automatic ticket, not two; a sixth in an hour is refused in words.
- [ ] Ask an agent "how much have I used this week": `stronghold__tool_usage_summary` reports only that account's usage.
- [ ] Ticket settings (Armory Admin page, served by Stronghold): change the hourly cap, reload; the value stays after a Stronghold restart.
- [ ] `/ticket` and `/usage` are gone from Ember's slash command list.
- [ ] Delete a test account: its tickets disappear from staff's list.

## 5. Outside clients [Plans 24, 24b]

- [ ] Create a client with `POST /api/admin/outside-clients` (staff session) and keep the key. `curl -H "Authorization: Bearer <key>" -H "Content-Type: application/json" -d '{"question":"Say hello"}' http://<host>:29601/api/outside/legion/ask` returns an answer and `usage.budget_remaining` falls. [24]
- [ ] Ask "list my notes" or "run a tool": the answer is text only and Legion's log shows no tool step. [24]
- [ ] A wrong key, a disabled client and a deleted client all answer the same 401 text. [24]
- [ ] A client with a budget of 1 token is refused on the second call with 429 and a `Retry-After`. [24]
- [ ] `ip_allow` set to another network gives 403, and the client's audit log shows `ip_not_allowed`. [24]
- [ ] With the main IP allow list set to the LAN only, an outside call from another network still reaches the route, while the admin app still refuses that network. [24]
- [ ] Stopping Legion makes the call 503 and the client's budget does not change. [24]
- [ ] The key and the question text appear nowhere in Portcullis logs or audit events. [24]
- [ ] A signed-in browser session cannot call `/api/outside/legion/ask`; an outside key cannot call `/api/chats` or any admin route. [24]
- [ ] Create a client with `stronghold` allowed. "remember that my cat is Tom", then in a second call "what is my cat's name?": the second answer uses the note. [24b]
- [ ] Stronghold's Brain folder has an `oc_...` folder with the note, and no other account's folder changed. [24b]
- [ ] Ask it to open a ticket, show usage, or learn a skill: it cannot, and nothing appears. Ask for a global note by name: it finds nothing. [24b]
- [ ] `/api/outside/stronghold/ask` with a legion-only client answers 403. Deleting the client removes its `oc_...` folder. [24b]

## 6. Brain and Ember screens [Plans 20e to 20k]

Run each on desktop, 768px, 767px and 375px, light and dark. Inputs and buttons are 44px high on a phone. Tab through every page and dialog; Esc closes them.

- [ ] **Memory control [20e].** Pin, unpin, remove, add; a too-long item shows the reason with the text kept; fill the stack to 80% and to full and read the warning on the closed button and in the panel; Compact now shows its busy state.
- [ ] **Notes [20f].** Folder buttons filter; search finds a word and clearing restores the list; create in the shown folder; a folder with capitals and spaces is cleaned; four levels keep Save off with the reason; edit and save shows "Saved."; change a file in a second window and use both conflict buttons.
- [ ] **Agent files [20f].** An agent-written file shows "Agent file" with no agent switch; editing shows "Edited" and Restore original brings the first text back; "Let agents edit this file" lets an agent change your own file and the off state blocks it.
- [ ] **Quota and loss [20f].** Delete a file; quota at 80% and full shows the line and refuses New file; leaving with unsaved edits asks first; a damaged `.md` file is counted as unreadable.
- [ ] **Sharing, sender [20g].** Share a copy of a file (button off with a reason while unsaved), share one section, share the same file again and read "already shared", share a skill, share a short-term item (Esc closes the dialog, then the panel).
- [ ] **Sharing, recipient (B) [20g].** Shares inbox: review a file (plain text, untrusted notice), Keep with a changed title and folder, find it on Notes with the sender; review a skill share, see it waiting for approval; decline one; block a sender (their waiting shares are declined) and see the same refusal as for an unknown name; unblock; withdraw a waiting share; check status words in "Sent by you".
- [ ] **Sharing limits [20g].** Fill the recipient's inbox limit or your pending limit and read the server's reason.
- [ ] **Proposals [20i].** Tell the agent a lasting preference and add a short-term item; it suggests or you ask; Notes shows "Suggestions (1)". Open it: plain text, "An agent wrote this" notice, nothing in Notes yet. Keep with a changed title and folder: the file appears with an agent as source. Decline one and the agent is told not to suggest it again. At the file limit, Keep shows the limit text and the suggestion stays. The action log has "Kept a suggestion" and "Declined a suggestion" without text. Another account sees none; deleting an account purges them.
- [ ] **Global brain [20k].** As member A: "Global" has the notice, Notes and Skills tabs, no Review queue, no edit controls; search finds a global file as plain text. As a `brain.global.write` account: create a global file (B then sees it), edit sends only changes, a stale save says the file changed, delete asks first; global skills show three groups with approve, retire, send back, edit, delete; share a file to global as A, approve it with a new title and folder as the writer, reject another.
- [ ] **Brain settings (Stronghold Admin) [20h].** Brain settings shows three cards and the brain folder path; an account without `settings.manage` is sent away; set Files per account small, Save, create files in Ember to the limit and read the refusal, raise it and create again without a restart; change one limit per card and see "changed from the defaults"; out-of-range, decimal and empty values show their words and Save stays off; the action log shows "Changed Stronghold brain settings" without values.

## 7. Record the result

- [ ] Note which steps failed and which were skipped, then bring them back as one list. A failed step becomes a fix plan; a passed section can be marked in the vault note for that plan.
- [ ] Decide the three 24b questions with live behaviour in hand: global-brain reads for outside clients (built "no"), writing as a per-client switch (built "always allowed"), recall switch (built "always on").

## Not in this runbook

- A real phone with the keyboard open, a Brain folder with thousands of files, and contrast beyond the computed pairs (Plan 20f and 20g left these unverified).
- Playwright e2e, which no plan ran.
