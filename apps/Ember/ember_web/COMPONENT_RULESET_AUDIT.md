# Ember Web component rules audit

This is the pre-correction baseline. See [COMPONENT_RULESET_FIXES.md](COMPONENT_RULESET_FIXES.md) for the implemented corrections and final verification; the findings and source line references below describe the original audited code.

Audit date: 2026-10-22. Source baseline: `a1f7d36e` on local `main`.

Inspected every Vue file under `ember_web/src`: **107 files (85 components, 21 views, and App.vue)**. Of these, 97 are runtime reachable and 10 are inactive renderers. Coverage includes inactive code; inactivity is not itself a rules violation. This audit changes documentation only.

**41 consolidated findings:** 1 P1, 36 P2, 4 P3. Findings group repeated causes and can affect several files. They are source-supported issues, not a claim that every scenario has been reproduced in a browser.

The highest priority is CHAT-01: an edit opened in one cached conversation can be submitted into another cached conversation after switching. The current store applies the edit and truncation to the active conversation. Bind editing state and submission to conversation identity before other cleanup.

## Authority and rule mapping

Project AGENTS.md and explicit user decisions take precedence. Applied the Brain query skill, Ember frontend design, design system (including component recipes), and mobile UI guide. The Brain project note supplies history; current source determines the runtime inventory.

[Brain: UI UX Frontend Rulesets](<D:/User/Documents/Programming/Brain/Maps/UI UX Frontend Rulesets.md>) · [Brain: ember_web](<D:/User/Documents/Programming/Brain/Projects/ember_web.md>) · [Frontend skill](<D:/User/Documents/Programming/Python/Citadel/.agents/skills/ember-frontend-design/SKILL.md>) · [Design system](<D:/User/Documents/Programming/Python/Citadel/.agents/skills/ember-design-system/SKILL.md>) · [Component recipes](<D:/User/Documents/Programming/Python/Citadel/.agents/skills/ember-design-system/components.md>) · [Mobile guide](<D:/User/Documents/Programming/Python/Citadel/.agents/skills/ember-frontend-design/mobile-ui.md>)

| Rule | Applied requirements and Brain sources |
| --- | --- |
| R1 | Semantic theme roles, shared color source and radius scale. [Color tokens should describe roles as well as palette values](<D:/User/Documents/Programming/Brain/Notes/Color tokens should describe roles as well as palette values.md>) |
| R2 | Accessible names, keyboard/focus behavior, navigation and panel semantics. [Navigation should preserve orientation and familiar controls](<D:/User/Documents/Programming/Brain/Notes/Navigation should preserve orientation and familiar controls.md>) |
| R3 | Labels, input behavior, validation timing and associated errors. [Forms should ask for little and explain errors in context](<D:/User/Documents/Programming/Brain/Notes/Forms should ask for little and explain errors in context.md>) |
| R4 | Truthful pending/success/failure feedback and recovery. [Feedback should acknowledge actions and support recovery](<D:/User/Documents/Programming/Brain/Notes/Feedback should acknowledge actions and support recovery.md>) |
| R5 | Request/scope identity, composition handling, draft retention and cleanup. [Search should debounce work and reject stale responses](<D:/User/Documents/Programming/Brain/Notes/Search should debounce work and reject stale responses.md>); [Motion should preserve control and readable content](<D:/User/Documents/Programming/Brain/Notes/Motion should preserve control and readable content.md>) |
| R6 | Severity-appropriate destructive confirmation and protected drafts. [Feedback should acknowledge actions and support recovery](<D:/User/Documents/Programming/Brain/Notes/Feedback should acknowledge actions and support recovery.md>) |
| R7 | View-owned scroll, responsive fit and effective 44px mobile targets. [Scroll patterns should fit the reading and navigation task](<D:/User/Documents/Programming/Brain/Notes/Scroll patterns should fit the reading and navigation task.md>) |
| R8 | Hierarchy, contrast, meaningful spacing and inert decoration. [Spacing should express relationships within a shared scale](<D:/User/Documents/Programming/Brain/Notes/Spacing should express relationships within a shared scale.md>); [Visual hierarchy should make the next action obvious](<D:/User/Documents/Programming/Brain/Notes/Visual hierarchy should make the next action obvious.md>); [Decorative surfaces should stay separate from content and controls](<D:/User/Documents/Programming/Brain/Notes/Decorative surfaces should stay separate from content and controls.md>); [UX laws are prompts for design checks rather than fixed limits](<D:/User/Documents/Programming/Brain/Notes/UX laws are prompts for design checks rather than fixed limits.md>) |
| R9 | Shared ownership, reuse and coordinated Admin counterparts. Citadel architecture conventions and source ownership test. |

Citadel motion policy takes precedence. Fixed backdrop/shadow colors, SVG artwork geometry and documented chart mark radius exceptions were evaluated in context, rather than treated as automatic violations.

## Verification evidence and limits

- TypeScript: `npx vue-tsc -b` passed.
- Unit suite: 159 test files, **2,079 tests passed**. Includes existing architecture and layout checks.
- Browser suite: **75 passed, 1 failed** on the first full run. The video workspace test reported an HTTP 405 console error; the mock agent-status endpoint returns 405. The isolated rerun passed (1 test). This is an intermittent test result, not a clean full-suite pass.
- Contrast calculation from current opaque sRGB tokens: white on light accent is **3.580:1**, light accent on surface is **3.315:1**, and dark primary text/accent is **6.886:1**. AuthCard uses the failing light pair for ordinary text. Other blended/hover/focus contexts need rendered measurements.
- Inventory checks: all 107 current Vue paths covered exactly once; source matches the audited snapshot; finding line references checked against current files.
- Existing automation does not certify each rule. Still pending: both themes; desktop, 768/767px and 375px; relevant 320px flows; long/enlarged text; effective target rectangles; keyboard and screen reader behavior; native dialog scrolling; device keyboard, zoom and rotation.

## Findings

<a id="chat-01"></a>

### CHAT-01 · P1 · Bind an edited message to its originating conversation

[src/features/chat/components/MessageList.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/MessageList.vue:164>) · R5, R6

The edit reset watches only busy/canChange, not conversation identity. ChatView reuses the unkeyed MessageList, and chat.ts selectChat skips loading for an already loaded idle chat. Edit question i in A, then open cached idle B: the editor/draft remains at i, and Save emits that index into B via editAndResend, potentially replacing B and truncating its later exchanges. A busy transition or a first-time transcript load does reset/unmount, but cached idle switches do neither.

**Suggested correction:** Pass a conversation identity, preserve the draft by chat or confirm discard on switching, clear edit confirmation on scope change, and validate the captured conversation/message identity before emitting an edit.

Evidence: Static source evidence; rendered check pending.

<a id="chat-02"></a>

### CHAT-02 · P2 · Make conversation rows keyboard operable

[src/features/chat/components/ChatRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatRow.vue:99>) · R2

The clickable li has no tabindex, interactive role, key handlers or link/button for selecting its conversation. The focusable actions button only opens the management menu; it cannot open the transcript. The same issue occurs in ConversationSidebar.vue:442-446 for search hits. Shared ancestor styles cannot add keyboard activation to either li.

**Suggested correction:** Use a destination link or dedicated row button with an accessible current state; keep the actions button a separate sibling. Apply the same change to search results.

Evidence: Static source evidence; rendered check pending.

<a id="chat-03"></a>

### CHAT-03 · P2 · Wait for IME composition before searching remotely

[src/features/chat/components/ConversationSidebar.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ConversationSidebar.vue:432>) · R5

Every input event immediately emits search, including composing events. chat.ts setSearch starts a debounce and guards request ordering, but receives only a string and cannot know whether composition is unfinished. A composition pause can therefore issue a search for unfinished text. There is also no explicit Enter submit path.

**Suggested correction:** Track compositionstart/compositionend, update displayed text immediately, issue remote work only after composition ends, and provide an explicit Enter search path while retaining the existing sequence guard.

Evidence: Static source evidence; rendered check pending.

<a id="chat-04"></a>

### CHAT-04 · P2 · Increase narrow sidebar icon hit widths

[src/features/chat/components/ChatRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatRow.vue:174>) · R7

ChatRow actions are fixed at 22px wide; ChatSection.vue:217 folder actions are 24px, ConversationSidebar.vue:606 new folder is 36px, and EntryAgentTag.vue:58 refresh is 24px. Global coarse-pointer CSS adds only min-height:44px. ChatView mobile overrides grow rows/search and header buttons, but none grows these widths or adds padded hit areas. All remain below Ember's 44 by 44 mobile target.

**Suggested correction:** Add effective 44px minimum width and height on mobile/coarse pointers for these controls, allowing their layout to reflow without overlapping neighbors.

Evidence: Static source evidence; rendered check pending.

<a id="chat-05"></a>

### CHAT-05 · P2 · Require typed confirmation when deleting a populated folder

[src/features/chat/components/FolderDialogs.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/FolderDialogs.vue:141>) · R6

The delete dialog says it deletes the folder and all its chatCount chats, but exposes only Cancel and DeleteButton. There is no typed check in confirmDelete. The sidebar delete-all action already uses requireText, so deleting the same collection through its folder bypasses that severity friction. This is a bulk transcript deletion, not just removing a folder label.

**Suggested correction:** Use typed confirmation for populated-folder deletion and place its destructive action in the final Danger zone; retain busy/error handling and focus on Cancel.

Evidence: Static source evidence; rendered check pending.

<a id="chat-06"></a>

### CHAT-06 · P2 · Preserve unsaved prompt edits across closing and Back

[src/features/chat/components/TemplatesModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TemplatesModal.vue:38>) · R5, R6

backToList clears the edit context unconditionally; Escape calls it and the close button emits close directly. Reopening runs startEdit from the original props.draft or opens the list. A later edit/new action overwrites name/body, so entered template changes disappear without Save/Discard confirmation. Keeping the modal component mounted does not preserve an addressable draft once editing is reset.

**Suggested correction:** Retain the current prompt draft until Save or an explicit Discard; prompt on Escape/close/Back when dirty and use a Stay/Cancel action that retains the edit.

Evidence: Static source evidence; rendered check pending.

<a id="chat-07"></a>

### CHAT-07 · P2 · Ignore save completions belonging to a previous prompt editor

[src/features/chat/components/TemplatesModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TemplatesModal.vue:66>) · R5, R4

Save disables its submit button but leaves Cancel and Close active. A user can leave saving prompt A, open/edit B (even close and reopen the modal), then A's response unconditionally calls backToList and destroys B's current edit context. A's rejection also writes its error into B. The templates store guards account changes, but that does not guard this modal session.

**Suggested correction:** Capture an editor/open generation and apply completion/error/finally updates only to that generation, or prevent leaving a pending editor while retaining its outcome and draft.

Evidence: Static source evidence; rendered check pending.

<a id="chat-08"></a>

### CHAT-08 · P2 · Apply generated titles to the option rows that were submitted

[src/features/chat/components/TriageQuestionModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TriageQuestionModal.vue:104>) · R5

generateTitles captures descriptions then writes results into the current rows by array index. Description/title inputs and Add/Remove option controls remain editable while titling is true, so removing a row or changing descriptions while the request runs assigns old titles to different/current options. Close is also allowed while titling. Only Generate and Ask are busy-disabled.

**Suggested correction:** Snapshot row keys and descriptions, reject superseded generation results, and update only unchanged matching rows; disable structural changes while generating if that is the intended interaction.

Evidence: Static source evidence; rendered check pending.

<a id="chat-09"></a>

### CHAT-09 · P2 · Do not resend edited questions during IME composition

[src/features/chat/components/MessageList.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/MessageList.vue:224>) · R5

The edited-question textarea binds keydown.enter.exact.prevent directly to saveEdit with no isComposing guard. Vue's exact modifier checks modifier keys, not IME state. Enter to confirm a composed character can therefore resend/truncate the exchange. ChatInput.onKeydown already explicitly guards composing Enter; the editor path bypasses it.

**Suggested correction:** Route edited-question Enter through a handler that ignores composing events before preventing default or saving; preserve Shift+Enter and Escape behavior.

Evidence: Static source evidence; rendered check pending.

<a id="chat-10"></a>

### CHAT-10 · P2 · Give the plain message editor a stable label

[src/features/chat/components/ChatInput.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatInput.vue:445>) · R3, R2

The normal textarea has only a dynamic placeholder and no associated label/aria-label. Its placeholder may be the predicted next question, so it does not reliably identify the field as the message composer. ListComposer explicitly labels its textbox Message, but that applies only after switching to list mode.

**Suggested correction:** Add a visible Message label, associated with the textarea and equivalent list editor, and a stable accessible name; keep the suggestion as supplementary content.

Evidence: Static source evidence; rendered check pending.

<a id="chat-11"></a>

### CHAT-11 · P2 · Retain ready attachments when running slash commands

[src/features/chat/components/ChatInput.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatInput.vue:341>) · R5

submit chooses an empty files list for slash commands so attachments should wait for a later question, as its comment states. It then clears draft before checking !isCommand, a computed derived from draft. That check is always true after clearing, so it removes all ready attachments even though none were sent with the command.

**Suggested correction:** Capture whether the submission is a command before clearing draft and use that captured value when deciding whether to remove ready attachments.

Evidence: Static source evidence; rendered check pending.

<a id="global-01"></a>

### GLOBAL-01 · P2 · Choose a text-safe light-theme accent pair

[src/style.css](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/style.css:12>) · R1, R8

The light theme uses #ffffff text on #e8590c, which calculates to 3.580:1. AuthCard.vue:79-80 uses that exact pair for ordinary-size primary button text. The same accent used for ordinary links gives 3.580:1 on the white background and 3.315:1 on the surface. The Brain/skill target is 4.5:1 for ordinary text; semantic token use alone does not satisfy it. Dark primary pair computes to 6.886:1.

**Suggested correction:** Choose and validate text-safe accent roles/pairs while preserving Ember identity; update both apps’ shared palette together and verify hovered/focused/mixed-color surfaces in both themes.

Admin counterparts: [style.css](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/style.css>).

Evidence: Computed from current opaque sRGB token pairs and verified AuthCard selector; other rendered/color-mix contexts remain pending.

<a id="o1"></a>

### O1 · P2 · Preserve unsent replies when switching tickets

[src/features/tickets/TicketsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/tickets/TicketsView.vue:161>) · R5, R6

loadDetail clears the single reply ref for every new ticket; selecting a different row after typing an unsent reply silently destroys it. The view also has no route-leave draft guard, so both new-ticket and reply drafts disappear on navigation.

**Suggested correction:** Keep replies per ticket and retain new-ticket drafts across navigation, or offer explicit Save/Discard/Stay handling before discarding.

Evidence: static source evidence; rendered check pending

<a id="o10"></a>

### O10 · P2 · Remove mobile hit-area overrides below 44px

[src/features/videoDownloader/components/FileRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/components/FileRow.vue:46>) · R7

Mobile CSS explicitly gives Save file and the icon action min-height40px. The named icon button's padding5px plus14px icon yields a width around24-26px; global button min-height cannot supply the missing width and loses to this scoped40px rule.

**Suggested correction:** Set effective width and height to44px minimum for icon actions and at least44px height for download links.

Evidence: static source evidence; rendered check pending

<a id="o11"></a>

### O11 · P2 · Keep Brain search and navigation targets at least 44px

[src/features/brains/BrainsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/brains/BrainsView.vue:288>) · R7

Mobile rules set Search min-height40px, breadcrumbs36px and Back40px (lines288,294,297), overriding the global44px button minimum. Short breadcrumbs also have no width minimum.

**Suggested correction:** Use effective44x44px touch targets for these controls without shrinking the available reading area.

Evidence: static source evidence; rendered check pending

<a id="o12"></a>

### O12 · P2 · Retain range keyboard focus in Firefox

[src/features/generator/GeneratorView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/generator/GeneratorView.vue:389>) · R2

The range focus rule removes the control outline, but its sole replacement is a ::-webkit-slider-thumb focus shadow at line390. Firefox's ::-moz-range-thumb receives no replacement, leaving the custom range without a visible focused state.

**Suggested correction:** Keep the control outline or supply an equivalent Firefox thumb focus treatment.

Evidence: static source evidence; rendered check pending

<a id="o13"></a>

### O13 · P2 · Export the range belonging to the loaded report

[src/features/usage/UsageView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/usage/UsageView.vue:180>) · R4, R5

A new period starts loading while the previous usage report stays displayed. Export remains enabled because it only checks !usage (line198); exportReport uses currentRange.label and range for metadata/name while exporting the previous usage.report. Exporting during the request mislabels the old data as the new period.

**Suggested correction:** Track the loaded period with its report and use that metadata for export, or disable Export until the selected period has loaded.

Evidence: static source evidence; rendered check pending

<a id="o15"></a>

### O15 · P2 · Give workspace panel modes tab semantics

[src/features/videoDownloader/VideoDownloaderView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/VideoDownloaderView.vue:76>) · R2

Download/Groups/My files and the desktop Single link/Download groups switch visible panels, but use SegmentedControl's group/aria-pressed buttons without tablist/tab/tabpanel relationships or arrow-key navigation. PdfMergerView:40 similarly switches Pages/Files panels using the value-selector control.

**Suggested correction:** Use an appropriate shared tab mode with tab roles, selected/tabindex state, panel relationships and arrow keys at these panel-switching call sites.

Evidence: static source evidence; rendered check pending

<a id="o2"></a>

### O2 · P2 · Reject publication reviews for the previous note

[src/features/notes/components/NotePromotionPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/notes/components/NotePromotionPanel.vue:44>) · R5

The props watcher at line33 clears review when noteId/sourceVersion changes, but open awaits refresh and review(id) and unconditionally assigns review at line52. Selecting another note while the request is pending can restore the old note's publication dialog under the newly selected note.

**Suggested correction:** Capture note identity/source version and a request generation; invalidate on prop changes and unmount, and reject stale review results.

Evidence: static source evidence; rendered check pending

<a id="o3"></a>

### O3 · P2 · Protect edited publication drafts on dialog close

[src/features/notes/components/NotePromotionPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/notes/components/NotePromotionPanel.vue:112>) · R5, R6

Closing the publication dialog sets review=null without checking edits to path/draft. Reopening open() overwrites both with generated values, so edited publication Markdown is silently discarded by Escape, backdrop, close, note selection or route departure.

**Suggested correction:** Track publication draft changes and retain them or confirm an explicit discard before replacing/closing the draft.

Evidence: static source evidence; rendered check pending

<a id="o4"></a>

### O4 · P2 · Keep pending extension saves attached to their dialog

[src/features/capabilities/components/UserExtensionModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/UserExtensionModal.vue:99>) · R4, R5

Close and Cancel remain active during saving, while save has no request/open identity guard. A user can close and open another extension before the first save resolves; the older saved event then closes the newer editor and selects the older extension. The submit control also omits aria-busy.

**Suggested correction:** Prevent closing/reopening during save or invalidate and ignore results from an older dialog session; expose busy state on the submit control.

Evidence: static source evidence; rendered check pending

<a id="o5"></a>

### O5 · P2 · Validate page ranges after the user finishes editing

[src/features/pdfMerger/components/SourceRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/SourceRow.vue:55>) · R3

Every input event calls setRange, which immediately parses and sets rangeError in stores/files.ts:92-103. Typing a valid range such as 1-3 temporarily shows an error after 1-. The rendered error at line57 has no id and the input has neither aria-invalid nor aria-describedby.

**Suggested correction:** Retain range text immediately but show validation on blur/submit; associate each range error with its own input.

Evidence: static source evidence; rendered check pending

<a id="o6"></a>

### O6 · P2 · Associate password mismatch with the confirmation field

[src/features/account/AccountView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/account/AccountView.vue:393>) · R3

passwordMismatch computes on each keystroke once confirm is nonempty (lines68-71), so the alert appears while a matching password is still being typed. The Repeat new password PasswordInput has no aria-invalid or described-by link to that error.

**Suggested correction:** Validate mismatch on blur/submit and give the repeat-password control an error id, aria-describedby and aria-invalid.

Evidence: static source evidence; rendered check pending

<a id="o7"></a>

### O7 · P2 · Expose progress on authentication actions

[src/features/auth/views/VerifyEmailView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/auth/views/VerifyEmailView.vue:62>) · R4

Verify and resend share busy and disable correctly, but Verify retains its static label and neither button exposes aria-busy or a progress indicator. LoginView:42 and RegisterView:65 change their button text but also omit aria-busy; their submit handlers have no early busy guard.

**Suggested correction:** Add aria-busy and visible pending feedback to each busy action, and guard submit/resend handlers against repeated calls.

Evidence: static source evidence; rendered check pending

<a id="o8"></a>

### O8 · P2 · Connect verification failures to the code input

[src/features/auth/views/VerifyEmailView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/auth/views/VerifyEmailView.vue:60>) · R3

Verification failures render as an unassociated paragraph. The code input at line58 has no aria-invalid or aria-describedby, so users focusing the invalid code do not receive its error context. Login and registration likewise render generic error paragraphs without announcements.

**Suggested correction:** Give code-validation errors a stable id and invalid/described-by state on the input; announce form-level login/registration failures while preserving entered values.

Evidence: static source evidence; rendered check pending

<a id="o9"></a>

### O9 · P2 · Give sidebar icon actions a 44px width

[src/features/settings/components/SidebarEditor.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/settings/components/SidebarEditor.vue:264>) · R7

The up/down/pin buttons have width28px and height28px with no mobile width override. Global coarse-pointer CSS only raises min-height to44px, leaving the hit area 28px wide.

**Suggested correction:** Expand each icon-button hit area to at least44px in both dimensions and reflow the row as necessary.

Admin counterparts: [SidebarEditor.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/SidebarEditor.vue>).

Evidence: static source evidence; rendered check pending

<a id="s1"></a>

### S1 · P2 · Reject stale dependent-option responses

[src/components/tools/forms/ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/ToolRunForm.vue:48>) · R5

loadOptions writes remote[field.name] after await without checking the dependency value or request identity. Choosing parent A, then B (or clearing it), allows a late A response to replace B options or the waiting state. The dependent select remains editable through these parent changes.

**Suggested correction:** Track a generation per field, invalidate on dependency changes/clear/unmount, and apply both successful and failed replies only for the current request.

Admin counterparts: [ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/ToolRunForm.vue>).

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s10"></a>

### S10 · P2 · Invalidate the selected bucket when series shrink

[src/components/analytics/LineChart.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/analytics/LineChart.vue:146>) · R5

The tooltip dereferences series[active]!.bucket without validating active against the current series. useBucketCursor keeps its active index when count changes. UsageView reuses this chart while loading a shorter period: hover the old chart after choosing a shorter range and let the reply arrive; an old index beyond the new length causes a render exception. No parent key resets the chart.

**Suggested correction:** Reset or clamp active whenever the series count changes, and guard the tooltip against a missing bucket. Preserve valid selection across same-size refreshes if desired.

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s11"></a>

### S11 · P2 · Contain wide generated result tables locally

[src/components/tools/gui/GuiResult.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/gui/GuiResult.vue:91>) · R2, R7

The result table has no local overflow wrapper, width cap, wrapping, or keyboard-reachable labeled scrolling region. API-driven column sets and long unbroken values can expand it beyond its narrow form/card; the view-level PageLayout scroller then owns horizontal overflow instead of a labeled result-table region.

**Suggested correction:** Wrap wide table output in a labeled keyboard-reachable local scroller with a width cap and suitable cell wrapping; verify long tool output at 375px.

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s2"></a>

### S2 · P2 · Use upload identity on both success and failure

[src/components/tools/forms/ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/ToolRunForm.vue:130>) · R4, R5

The success guard compares filenames, so two replacements with the same filename can install an older server path. The catch branch has no guard at all: an older failed upload can overwrite a newer uploading/done state, remove the uploading lock, and misreport the selected file. The file input/drop target permits replacement during upload.

**Suggested correction:** Use a per-field request token rather than filename, check it in success/catch/finalization, and invalidate pending work on teardown.

Admin counterparts: [ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/ToolRunForm.vue>).

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s3"></a>

### S3 · P2 · Make daily heatmap values reachable by keyboard

[src/components/analytics/UsageHeatmap.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/analytics/UsageHeatmap.vue:29>) · R2, R7

Daily values are exposed only through pointerenter/pointerleave on unfocusable spans. The details area asks users to hover; there is no keyboard selection or table alternative. aria-label on a generic span does not supply an interactive keyboard path.

**Suggested correction:** Provide a focusable chart with arrow-key day navigation and selection/focus feedback, or an accessible daily table; preserve a usable touch path without creating hundreds of tiny tab stops.

Admin counterparts: [UsageHeatmap.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/UsageHeatmap.vue>).

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s4"></a>

### S4 · P2 · Show recoverable clipboard failure in tool results

[src/components/tools/gui/GuiResult.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/gui/GuiResult.vue:41>) · R4, R5

GuiResult.copy catches clipboard rejection without any visible state. ToolResultPanel.vue:32-34 repeats the same silent failure. In a blocked clipboard context the user presses Copy and receives no explanation or recovery, unlike the shared CopyButton which already reports Copy failed. Both implementations also leave feedback timers unowned.

**Suggested correction:** Reuse the shared clipboard helper/feedback pattern, show failure with a retry or selectable-text recovery, and own/clear feedback timers.

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s5"></a>

### S5 · P2 · Give compact shared actions a full touch target

[src/components/ui/buttons/ActionButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/buttons/ActionButton.vue:82>) · R7

ActionButton icon-only/mobile styling yields a 14px icon plus 6px padding and borders (28px width). CopyButton has a 14px icon plus 12px horizontal padding (26px). SettingRow reset is 28px wide, BaseModal close has only a glyph plus native padding (inactive IntegrationToolsModal explicitly caps it at 32px), TagInput chip removal has zero padding, and GuiResult icons are 34px wide. Global coarse-pointer CSS supplies button height only; inspected consumers do not consistently expand widths. Inactive OpenPageButton also becomes a 28px square anchor below 480px and receives no global button minimum. Some consumers, including ChatHeader and ToolRunModal command copy, explicitly expand their targets.

**Suggested correction:** Add coarse-pointer min-width/min-height of at least 44px at the shared controls, retaining compact artwork and separated adjacent targets; include OpenPageButton links, modal close, tag removal and GuiResult icon actions.

Admin counterparts: [ActionButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/ActionButton.vue>), [CopyButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/CopyButton.vue>), [SettingRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/SettingRow.vue>), [BaseModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/BaseModal.vue>).

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s6"></a>

### S6 · P2 · Expand switch labels into touch targets

[src/components/ui/forms/ToggleSwitch.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/ToggleSwitch.vue:36>) · R7

Small switches use a 32x18px track and an inline-flex label with no padding/minimum. SettingsView passes aria-label and no slot for multiple small switches, so their effective target is exactly 32x18px. The global button minimum does not apply to this label and its hidden 1px input. The inactive LockSwitch copy similarly uses a 62x30px label without a height minimum.

**Suggested correction:** Give the label an effective 44x44px coarse-pointer hit area while preserving the track dimensions, and check spacing between switches; apply the corresponding minimum to LockSwitch before reuse.

Admin counterparts: [ToggleSwitch.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/ToggleSwitch.vue>).

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s7"></a>

### S7 · P2 · Ignore composition confirmation keys in tag entry

[src/components/ui/forms/TagInput.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/TagInput.vue:97>) · R3, R5

onKey handles Enter/comma and prevents default without checking event.isComposing. Confirming a candidate with Enter in an IME can commit/clear the unfinished text as a tag or choose a suggestion instead of letting composition finish.

**Suggested correction:** Ignore tag navigation/commit shortcuts during composition (including the composition-confirming Enter path), retaining native composition before committing a tag.

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s8"></a>

### S8 · P2 · Associate validation messages with their controls

[src/components/tools/forms/ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/ToolRunForm.vue:279>) · R3

ToolRunForm renders field-specific errors as anonymous small elements and communicates invalidity only through a CSS class; inputs/selects/textareas lack aria-invalid and aria-describedby. TagInput.vue:142-176 likewise shows a component-local error without linking it to its combobox. Field names appear in messages visually but assistive technology cannot discover the error relationship when returning to the field.

**Suggested correction:** Give validation messages unique instance-scoped IDs, connect them with aria-describedby and set aria-invalid while invalid; retain descriptions and remote-option failure hints in those associations.

Admin counterparts: [ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_admin/src/components/ToolRunForm.vue>).

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="s9"></a>

### S9 · P2 · Name the slash-command dialog

[src/components/tools/forms/CommandFormModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/CommandFormModal.vue:34>) · R2, R9

The native dialog has neither aria-label nor aria-labelledby. Its visible h3 is not referenced, so the modal lacks a programmatic name even though the close button and underlying parameter fields are named.

**Suggested correction:** Use BaseModal with the command as its title, or assign a unique heading ID and aria-labelledby on the dialog.

Evidence: Static source evidence and consumer/global-style inspection; rendered check pending.

<a id="chat-13"></a>

### CHAT-13 · P3 · Expose pending decisions on the activated controls

[src/features/chat/components/QuestionCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/QuestionCard.vue:114>) · R4

QuestionCard Submit/Skip become disabled while answering but keep their idle labels and have no aria-busy or progress. MessageList.vue:342-356 approval buttons similarly only disable while deciding. ShareDialog.vue:135, TemplatesModal.vue:114 and FolderDialogs.vue:138 do change their labels and guard repeats, but omit aria-busy/progress on their busy submit controls. No wrapper supplies these controls with busy state.

**Suggested correction:** Bind aria-busy and visible in-control pending feedback to answering/deciding and submit pending flags; retain duplicate-submission guards and show success only after server confirmation.

Evidence: Static source evidence; rendered check pending.

<a id="chat-14"></a>

### CHAT-14 · P3 · Move context chart colors into the shared token source

[src/features/chat/components/ContextPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ContextPanel.vue:117>) · R1

The component defines four palette roles with literal light-dark hex values (agents, builtin_tools, mcp_tools, messages) outside style.css. These are CSS categorical chart colors, not SVG geometry or the permitted fixed black shadow/backdrop values. Labeling rows avoids color-only meaning but does not satisfy the Citadel token-source rule.

**Suggested correction:** Define the categorical context roles in the shared theme/token source and consume them here; align both apps' token sources when introducing shared tokens.

Evidence: Static source evidence; rendered check pending.

<a id="o14"></a>

### O14 · P3 · Reconcile local-setting save behavior with the UI policy

[src/features/settings/SettingsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/settings/SettingsView.vue:41>) · R4

SCOPE_NOTE says local settings apply on Save, theme and browser-local chat preferences are drafts, and save() applies them at lines265-275. The Ember skills and accepted Brain decision require browser-local preferences to apply instantly. The existing explicit Save is still appropriate for account/server choices.

**Suggested correction:** Reconcile and document the intended local-setting policy; align browser-local behavior/copy with that decision while preserving server/account draft protection.

Evidence: static source evidence; rendered check pending

<a id="o16"></a>

### O16 · P3 · Represent the resource request as pending

[src/features/capabilities/components/ResourceReader.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/ResourceReader.vue:13>) · R4

The reading prop identifies the selected resource URI, rather than request pending state. The Read control has no pending flag, disabled state, aria-busy or on-control progress. CapabilitiesView.read issues a new request on every submission; its generation guard keeps results ordered but repeated Read clicks still send overlapping work.

**Suggested correction:** Track resource-request pending state, disable/guard the active submission and show aria-busy plus progress.

Evidence: static source evidence; rendered check pending

## Rules and documentation alignment

- **Local settings:** O14 conflicts with the accepted [local-versus-account settings decision](<D:/User/Documents/Programming/Brain/Notes/Decision - settings that reach other accounts save explicitly, local ones apply instantly.md>) and frontend skill. SettingsView currently drafts browser-local settings until Save. Reconcile the intended policy before changing it; preserve protection for account/server drafts.
- **Panel tabs:** the component recipe describes a plain segmented group for “period, tab”, while the frontend skill requires proper tab semantics for panel navigation. Clarify this distinction: exclusive value pickers can remain groups; workspace panel navigation needs the tab interaction model (O15).
- **Moved paths:** frontend skill references still include the former root `components/pageLayout.css`, `components/ConfirmModal.vue`, root views and videoDownloader component locations. Current paths live under `components/layout`, `components/ui/dialogs`, and `features`. These references need a separate documentation update.
- **Project note:** Brain/Projects/ember_web.md retains historical page/path/test inventory. It should be synced separately; it was not treated as proof of current behavior.
- **Excluded hypothesis:** a suspected SharedChatView late-response title overwrite was not established because it already checks the live route token. It is not counted as a confirmed finding. Retain navigation-away testing as a follow-up.

## Per-file coverage

“No local finding” means no additional source-supported issue was identified in that file. It is not a visual/accessibility pass. Shared/global findings can apply through consumers. GLOBAL-01 affects the palette throughout the app, including AuthCard; inherited form/control issues are listed at their owning component.

| File | Reachability | Local findings | Rules inspected | Evidence and remaining limits |
| --- | --- | --- | --- | --- |
| [App.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/App.vue>) | Active | No local finding | R2, R5, R7, R8, R9 | Account-keyed KeepAlive, protected/public routing, centralized visualViewport sizing with scale handling and listener cleanup, flex min-width/min-height. Source inspection; keyboard/device geometry remains pending. |
| [components/analytics/LineChart.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/analytics/LineChart.vue>) | Active | [S10](#s10) | R1, R2, R5, R7, R8 | Inspected axis/legend/table twin, keyboard cursor helper, chart.css, preserved loading display, and UsageView range consumer. Chart mark radius exceptions retained; selected-index invalidation is missing. |
| [components/analytics/UsageHeatmap.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/analytics/UsageHeatmap.vue>) | Active | [S3](#s3) | R1, R2, R7, R8 | Inspected day grid, UTC value labels, hover details, legend and overflow. 11px marks use the documented 2px radius exception; daily values have no keyboard path. |
| [components/auth/AuthCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/auth/AuthCard.vue>) | Active | No local finding | R1, R3, R7, R8 | Inspected scrollable card shell and deep form/input/button styling. Field labels/errors are supplied by auth consumers; palette contrast is tracked separately by GLOBAL-01. Keyboard viewport fit remains rendered-only. |
| [components/content/ChatAttachment.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/content/ChatAttachment.vue>) | Active | No local finding | R1, R2, R4, R5, R7 | Inspected bounded authenticated image IDs, download-permission branch, image-error recovery, attachment-change reset, native details and named enlargement button/modal; text previews wrap and scroll locally. |
| [components/content/DownloadCards.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/content/DownloadCards.vue>) | Active | No local finding | R1, R2, R4, R7 | Inspected permission-gated download anchors, explicit unavailable text, format/size metadata and shared token styles. Long filenames and touch dimensions across consumers need rendered checks; no unsupported universal overflow claim made. |
| [components/content/MarkdownContent.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/content/MarkdownContent.vue>) | Active | No local finding | R1, R2, R4, R7 | Inspected sanitized render helper integration, delegated code-copy feedback, connected-element timeout guard, hover/focus/touch visibility and local code/table overflow. Clipboard failure is explicit; keyboard scroller discovery and long content remain pending. |
| [components/layout/AccountMenu.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/layout/AccountMenu.vue>) | Active | No local finding | R1, R2, R5, R7 | Inspected semantic link/action rows, arrow/Home/End/Escape handling, route/outside close, focus return and listener teardown. Menu is nonmodal; mobile rail hides this desktop menu. Short-height menu fit and focus contrast need rendering. |
| [components/layout/EmberLogo.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/layout/EmberLogo.vue>) | Active | No local finding | R1, R8 | Inspected token-colored aria-hidden SVG artwork and decorative flame/orbit animation. It contains no auto-moving informational content; Citadel animation policy applies. |
| [components/layout/NavRail.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/layout/NavRail.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R9 | Inspected desktop vs 767px mobile navigation, link labels/current styles, 44px mobile tabs, theme/account composition, sequence/account guards for unread counts and listener/interval cleanup. Layout imports are permitted composition. |
| [components/layout/PageLayout.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/layout/PageLayout.vue>) | Active | No local finding | R1, R2, R7, R8 | Inspected heading/description/actions/toolbar slots and imported pageLayout.css: view owns overflow, fill mode carries min-height/min-width, header reflows on mobile. Slot-specific issues belong to consumers. |
| [components/layout/PwaStatus.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/layout/PwaStatus.vue>) | Active | No local finding | R1, R2, R4, R5, R7 | Inspected install/update guards, aria-busy, error recovery, deferred cross-tab update, explicit save-before-reload wording and event teardown. Coarse-pointer minimum heights are supplied; browser-specific install/viewport behavior remains pending. |
| [components/tools/ToolResultPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/ToolResultPanel.vue>) | Active | [S4](#s4) | R1, R2, R4, R5, R7 | Inspected JSON/Markdown formatting, raw toggle, explicit error text, clipboard copy and scrollable JSON output. Clipboard failure is silent, unlike shared CopyButton. Local raw-data scroller keyboard discoverability remains a pending check. |
| [components/tools/catalog/IntegrationToolsModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/catalog/IntegrationToolsModal.vue>) | Inactive | [S5](#s5) | R1, R2, R4, R5, R7 | Inspected tool search/selection/run, generation guard on results, capability/permission reset, offline/read-only branches, desktop panes and mobile grid. Uses shared form/modal; 32px close width participates in S5. Search is cheap local filtering, so no remote IME/debounce finding. |
| [components/tools/catalog/ToolCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/catalog/ToolCard.vue>) | Inactive | No local finding | R1, R2, R7, R9 | Inactive: no production import found. Inspected real button trigger with aria-haspopup, tool label/name and token row styles; no source-proven issue beyond pending long-label rendering. |
| [components/tools/forms/CommandFormModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/CommandFormModal.vue>) | Active | [S9](#s9) | R1, R2, R3, R7, R9 | Inspected native dialog opening, command-text submission, keyed parameter form and scroll sizing. Dialog lacks a programmatic name; shared form findings also affect its parameters. Initial mount/keyboard viewport behavior needs rendering. |
| [components/tools/forms/ToolRunForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/ToolRunForm.vue>) | Active | [S1](#s1), [S2](#s2), [S8](#s8) | R1, R2, R3, R4, R5, R7 | Inspected schema-derived fields/defaults, dependency reloads, file replacement, buildArgs validation, permissions and live/manual submit paths. Inputs retain values on failed submit, but request ownership and error associations are incomplete. |
| [components/tools/forms/ToolRunModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/forms/ToolRunModal.vue>) | Active | No local finding | R1, R2, R3, R4, R7 | Inspected named BaseModal, keyed form per tool, command copy and result rendering; CapabilitiesView guards close while running. This component explicitly expands command-copy targets to 44px. Parameter findings are owned by ToolRunForm. |
| [components/tools/gui/GuiFormSection.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/gui/GuiFormSection.vue>) | Active | No local finding | R1, R4, R5, R7 | Inspected latest-run/disposed guards, countdown/debounce disposal and KeepAlive deactivate/reactivate behavior. Existing result survives pending refresh; API error clears it and displays error. Embedded visual ordering and viewport fit remain pending. |
| [components/tools/gui/GuiResult.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/gui/GuiResult.vue>) | Active | [S11](#s11), [S4](#s4), [S5](#s5) | R1, R2, R4, R5, R7 | Inspected secret show/copy/regenerate, strength icon-independent labels, message/table/scalar branches and compact actions. Clipboard failure is silent, icons are 34px wide and dynamic tables lack local containment. |
| [components/tools/gui/GuiTabsSection.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/tools/gui/GuiTabsSection.vue>) | Active | No local finding | R1, R2, R5, R7 | Inspected tab/tabpanel IDs, roving tabindex, arrows/Home/End, named panel and KeepAlive form persistence. Tabs scroll locally and use native buttons; render long labels and text enlargement before certifying fit. |
| [components/ui/buttons/ActionButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/buttons/ActionButton.vue>) | Active | [S5](#s5) | R1, R2, R7 | Inspected native button/slot name, focus ring, disabled styling and responsive label hiding. Mobile/icon-only padding yields a compact width despite global button height. Consumer-specific 44px override in ChatHeader is acknowledged. |
| [components/ui/buttons/CopyButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/buttons/CopyButton.vue>) | Active | [S5](#s5) | R1, R2, R4, R5, R7 | Inspected accessible name, shared clipboard helper, explicit success/failure, timed reset and timer teardown. Generic icon width is only 26px; some consumers expand it and others do not. Async copy feedback after teardown is low impact, not separately flagged. |
| [components/ui/buttons/DeleteButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/buttons/DeleteButton.vue>) | Active | No local finding | R1, R2, R4, R6, R8 | Inspected destructive outline pill, guarded click, aria-busy/aria-disabled, prop-driven collapse animation, native disabled behavior and decoration pointer-events. Confirmation/severity belongs to callers; animation does not gate the request. |
| [components/ui/buttons/OpenPageButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/buttons/OpenPageButton.vue>) | Inactive | [S5](#s5) | R1, R2, R7 | Inspected internal RouterLink/external anchor semantics, rel protections, preserved screen-reader label and focus ring. The small-screen icon link becomes 28x28px and has no global anchor size floor. |
| [components/ui/buttons/SaveButton.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/buttons/SaveButton.vue>) | Active | No local finding | R1, R2, R4, R7 | Inspected parent-owned saved toggle, visible text, aria-pressed, disabled fallthrough and focus ring; heart is decorative. Button height receives the global coarse-pointer floor; no static false success claim. |
| [components/ui/dialogs/BaseModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/dialogs/BaseModal.vue>) | Active | [S5](#s5) | R1, R2, R5, R7 | Inspected native showModal focus behavior, title name, Escape/backdrop close and native-close echo guard; max-height and overflow preserve scrolling. Close target lacks width floor; actual keyboard viewport positioning remains pending. |
| [components/ui/dialogs/ConfirmModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/dialogs/ConfirmModal.vue>) | Active | No local finding | R1, R2, R3, R4, R6, R7 | Inspected named BaseModal, requireText matching/reset, busy-confirm guard, cancel disabling and outlined DeleteButton for danger. Parent close guards vary; no blanket claim that closing always loses/cancels pending work. Severe-action policy is caller-owned. |
| [components/ui/forms/LockSwitch.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/LockSwitch.vue>) | Inactive | [S6](#s6) | R1, R2, R7, R9 | Inactive: no production import found. Inspected real checkbox role=switch, attrs/slot label contract, focus outline and disabled behavior. Track is 62x30px with no coarse-pointer label expansion; note within S6 before reuse. |
| [components/ui/forms/PasswordInput.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/PasswordInput.vue>) | Active | No local finding | R1, R2, R3, R7 | Inspected unique generated input ID, explicit label, forwarded autocomplete/error attributes, reveal state/aria-controls, disabled propagation and 44px input/56px reveal target. Field-specific validation belongs to consumers. |
| [components/ui/forms/SegmentedControl.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/SegmentedControl.vue>) | Active | No local finding | R1, R2, R5, R7, R8 | Inspected native aria-pressed button group, disabled options, reactive measurement, ResizeObserver disposal and pointer-free thumb. Value selectors are valid groups; actual panel-selector semantics require consumer review and are not blanket failures here. |
| [components/ui/forms/SettingRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/SettingRow.vue>) | Active | [S5](#s5) | R1, R2, R4, R7 | Inspected label/description/cost grouping, modified marker plus screen-reader text and reset action name. Slots own settings values/persistence. Reset is explicitly 28px wide and is not expanded by consumer CSS. |
| [components/ui/forms/TagInput.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/TagInput.vue>) | Active | [S5](#s5), [S7](#s7), [S8](#s8) | R1, R2, R3, R5, R7 | Inspected local known-tag filtering, combobox/listbox active-descendant navigation, chip add/remove, blur commit and error states. Composition keys are not guarded; errors are not linked; chip delete hit area has zero padding. |
| [components/ui/forms/ToggleSwitch.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/forms/ToggleSwitch.vue>) | Active | [S6](#s6) | R1, R2, R4, R7 | Inspected checkbox role=switch, label/attrs forwarding, ON/OFF and knob position, disabled state and focus outline. White knob is the documented switch pattern, not an automatic palette failure. Label-only targets remain undersized in active small Settings switches. |
| [components/ui/menus/PopupMenu.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/menus/PopupMenu.vue>) | Active | No local finding | R1, R2, R5, R7 | Inspected nonmodal teleport menu/flyouts, role/checked/disabled state, arrows/Home/End/Escape/Tab, outside/resize close, positioning and listener disposal. Focus-background contrast, long menu height and keyboard viewport placement require rendered checks. |
| [components/ui/status/CountdownRing.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/status/CountdownRing.vue>) | Active | No local finding | R1, R4, R8 | Inspected bounded remaining/total fraction and aria-hidden decorative ring. GuiFormSection supplies the visible seconds; essential countdown is not a content carousel and needs no new motion setting. |
| [components/ui/status/ElapsedTime.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/status/ElapsedTime.vue>) | Active | No local finding | R1, R5, R8 | Inspected reactive since prop, tabular clock and useElapsed integration. Helper owns ticker lifecycle; a running status clock is not a decorative marquee. |
| [components/ui/status/IconTile.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/components/ui/status/IconTile.vue>) | Inactive | No local finding | R1, R2, R7, R8, R9 | Inactive: no production import found. Inspected destination link vs action button, visible label/subtitle, focus ring and token SVG art. Decoration sits in its own art span and does not overlay neighboring controls; no speculative interception finding. |
| [features/account/AccountView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/account/AccountView.vue>) | Active | [O6](#o6) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed identity/security/device sections, disclosure forms, busy control feedback, device confirmation, tokens/focus and responsive grid. O6 password validation timing and error association. Source-only inspection; no visual or device pass is implied. |
| [features/agents/AgentsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/agents/AgentsView.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Active routed agent listing reviewed: interval setup/cleanup, refresh disabling, read-only cards, token grid and feedback. Network overlap possible for >15s requests; not elevated without clearer user-visible trigger. Source-only inspection; no visual or device pass is implied. |
| [features/agents/components/AgentCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/agents/components/AgentCard.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed named full-card dialog trigger, replacement inset focus indicator, icon/text status and clamped preview with full-description modal; token styles. Source-only inspection; no visual or device pass is implied. |
| [features/agents/components/AgentLlm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/agents/components/AgentLlm.vue>) | Active | No local finding | R1, R2, R4, R5, R6, R7, R8, R9 | Active AgentCard child reviewed: semantic definition list and model tiers, wrapping ids, token secondary text; use_for descriptions exist only as native titles. Source-only inspection; no visual or device pass is implied. |
| [features/agents/components/AgentMap.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/agents/components/AgentMap.vue>) | Inactive | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Inactive: no non-test importer found. Reviewed inferred-edge disclosure, pressed selected nodes, labeled status, scroll container and focus styles; no automatic literal SVG/radius finding. Labeled keyboard local scrolling requires rendered verification if revived. Source-only inspection; no visual or device pass is implied. |
| [features/auth/views/LoginView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/auth/views/LoginView.vue>) | Active | [O7](#o7), [O8](#o8) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed visible username/password labels, autocomplete and retained failure values; submit text/disable present, O7/O8 feedback limitations. Source-only inspection; no visual or device pass is implied. |
| [features/auth/views/NoAccessView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/auth/views/NoAccessView.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed read-only AuthCard title/subtitle and exemption from PageLayout; no interactive component-specific finding. Source-only inspection; no visual or device pass is implied. |
| [features/auth/views/RegisterView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/auth/views/RegisterView.vue>) | Active | [O7](#o7), [O8](#o8) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed visible labels, username/email/password autocomplete/type/native constraints, retained failure values and auth routing; shares O7/O8 auth feedback cause. Source-only inspection; no visual or device pass is implied. |
| [features/auth/views/VerifyEmailView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/auth/views/VerifyEmailView.vue>) | Active | [O7](#o7), [O8](#o8) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed retained code, shared disabled busy state, resend/verify/error messages and AuthCard styles. O7/O8. Source-only inspection; no visual or device pass is implied. |
| [features/brains/BrainsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/brains/BrainsView.vue>) | Active | [O11](#o11) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed explicit-submit search, busy-disabled scope/query, private clearing in resetScope, origin-scope hit opening, retained document and modal placement. No debounce/IME claim made for explicit-submit-only search; O11 target CSS. Source-only inspection; no visual or device pass is implied. |
| [features/brains/components/BrainConnectionForm.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/brains/components/BrainConnectionForm.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed saved-vs-draft server settings, disabled fieldset while fetching/saving, URL/password types, retained errors, notice and labeled switches; section-level aria-busy present. Copy exists in Admin. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/components/CapabilityCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/CapabilityCard.vue>) | Inactive | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Inactive: no non-test importer found. Reviewed card dialog button, inset focus replacement, status text/icon and switch/link stacking over stretched hit area. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/components/CapabilitySection.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/CapabilitySection.vue>) | Inactive | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Inactive render component: only SectionPage type is imported. Reviewed disclosure button/state, label/status summaries, token styles and legacy switch contract; no runtime certification. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/components/ResourceReader.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/ResourceReader.vue>) | Active | [O16](#o16) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Active resource form reviewed with parent generation guard, label and Markdown output; O16 pending UI. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/components/SupermarketItem.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/SupermarketItem.vue>) | Inactive | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Inactive: no non-test importer found. Reviewed add/disable accessible names, icon/text Added status, token rows and wrapping; legacy component lacks request-pending contract but active catalog does not use it. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/components/UserExtensionModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/components/UserExtensionModal.vue>) | Active | [O4](#o4) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed labels and URL type, masked header values, host-change warning, retained save errors and modal lifecycle; O4 pending dialog identity. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/views/CapabilitiesView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/views/CapabilitiesView.vue>) | Active | [O4](#o4), [O16](#o16) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed real tablist arrow/Home/End behavior, local filtering/per-tab state, mobile focus return, confirmed switch state, resource/run generation guards and modal placement. O4/O16 flow owners. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/views/CapabilityPageView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/views/CapabilityPageView.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed route-name sequence guard, upfront old-page clearing, enabled-capability check and dynamic sections; delegated forms/tabs are parent audit scope. Source-only inspection; no visual or device pass is implied. |
| [features/capabilities/views/SupermarketView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/capabilities/views/SupermarketView.vue>) | Inactive | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Inactive compatibility component: router redirects before rendering. Reviewed onMounted Router replacement preserving query/hash and announced opening text. Source-only inspection; no visual or device pass is implied. |
| [features/chat/components/AgentActivity.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/AgentActivity.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Reactive agent chain and elapsed status, tiny essential busy pulse; tokenized appearance. No content carousel or user action. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ApprovalModePicker.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ApprovalModePicker.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Nonmodal menu uses menuitemradio, arrows/Escape/Tab and listener cleanup; allow-all uses ConfirmModal. Mobile composer supplies menu sizing and chip height. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ChatHeader.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatHeader.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Destination/actions use shared buttons and popup menu; context meter has numeric progress semantics, outside/Escape cleanup and labels. Mobile parent menu placement inspected. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ChatInput.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatInput.vue>) | Active | [CHAT-10](#chat-10), [CHAT-11](#chat-11) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Composer IME send guard, autocomplete arrows, draft restoration, pending attachment state, mobile controls and parent popovers inspected. List mode supplies its own textbox label. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ChatRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatRow.vue>) | Active | [CHAT-02](#chat-02), [CHAT-04](#chat-04) | R1, R2, R4, R5, R7, R8 | Rename drafts have Enter/Escape/blur single-save handling and named menu trigger; parent styles supply row box; pointer-only selection and small action width verified. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ChatSection.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatSection.vue>) | Active | [CHAT-04](#chat-04) | R1, R2, R4, R5, R7, R8 | Folder disclosure uses aria-expanded and native button, drag state clears on cancellation; menu has name/expanded semantics. Small menu width verified. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ChatSettingsMenu.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ChatSettingsMenu.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Nonmodal group with outside/Escape cleanup; local preferences documented; second-brain toggle delegates pending state to server-confirmed store and shared switch. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ContextPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ContextPanel.vue>) | Active | [CHAT-14](#chat-14) | R1, R2, R4, R5, R7, R8 | Stacked chart has text/numeric rows; nonmodal dialog does not trap focus or lock scroll; accuracy uses shared segmented control. Local palette definitions inspected. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ConversationSidebar.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ConversationSidebar.vue>) | Active | [CHAT-03](#chat-03), [CHAT-02](#chat-02), [CHAT-04](#chat-04) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Search/list/selection/deletion/drag flows and timers inspected; delete-all has typed ConfirmModal, local popup ownership guards exist. Search sequence guard lives in chat store. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/EntryAgentTag.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/EntryAgentTag.vue>) | Active | [CHAT-04](#chat-04) | R1, R2, R4, R5, R7, R8 | Load/error/unavailable text and disabled spinning refresh are present; named with title. No inherited mobile width correction found. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/FolderDialogs.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/FolderDialogs.vue>) | Active | [CHAT-05](#chat-05), [CHAT-13](#chat-13) | R1, R2, R4, R5, R7, R8 | Shared BaseModal, retained API errors, busy close guard and per-mode identity checks inspected; folder delete removes contained chats. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ListComposer.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ListComposer.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Tiptap textbox has Message accessible name and multiline semantics, paste allows text, IME handler and editor destruction present. Parent .box:focus-within supplies visible editing state. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/MessageList.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/MessageList.vue>) | Active | [CHAT-01](#chat-01), [CHAT-09](#chat-09), [CHAT-13](#chat-13) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Local scroll, scroll composable, approval/question disabling, inline editing and truncation confirmation inspected; store cached-chat switch path verified. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/PlanPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/PlanPanel.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Read-only checklist pairs status marks with text, tokenized cards and wrapping item text. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/QuestionCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/QuestionCard.vue>) | Active | [CHAT-13](#chat-13) | R1, R2, R4, R5, R7, R8 | Native selection buttons expose aria-pressed, Other text has a contextual accessible name, answering disables controls; pending control feedback inspected. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ShareDialog.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ShareDialog.vue>) | Active | [CHAT-13](#chat-13) | R1, R2, R4, R5, R7, R8 | Native dialog, creation guard, generation-scoped list/create/revoke results, one-time link copy and revoke confirmation inspected. Black backdrop/shadow explicitly permitted. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/TemplatePicker.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TemplatePicker.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Cheap local filtering correctly immediate; native option buttons, named trigger, outside listener cleanup and nonmodal popover inspected. ChatInput mobile overrides supply trigger width/popup bounds. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/TemplatesModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TemplatesModal.vue>) | Active | [CHAT-06](#chat-06), [CHAT-07](#chat-07), [CHAT-13](#chat-13) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Labeled fields and max lengths, server error retention, delete confirmation and async store account guards inspected; modal session/draft guards missing as recorded. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/ToolSteps.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/ToolSteps.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Native nested details for trace with tool status symbols, explicit failure count, wrapping argument/result blocks, live delegate state inspected. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/TriageQuestionModal.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TriageQuestionModal.vue>) | Active | [CHAT-08](#chat-08) | R1, R2, R4, R5, R7, R8 | Labeled main fields, option accessible names, submit/titling busy flags, recoverable errors and draft retention on close inspected; mutable options during generated-title request verified. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/TurnNotices.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/TurnNotices.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Textual status list and native Dismiss button, tokenized wrapping banner and explicit focus style. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/UsageChip.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/UsageChip.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Native disclosure button with aria-expanded and Escape, read-only definition list with wrapping values; tokenized panel. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/UsageGauges.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/UsageGauges.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Numeric usage and progressbar labels supplement color, request sequence guards latest load and failures retain prior data. Freshness/contrast remain rendered/product checks. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/components/WelcomeCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/components/WelcomeCard.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Read-only empty state, derived command tips and greeting, tokenized typography; large top spacing requires rendered viewport check. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/views/ChatView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/views/ChatView.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Chat PageLayout exemption verified; shell/min-height scrolling, cached view, mobile drawer focus restoration, dialogs outside hidden drawer, store feedback and composer overrides inspected. Drawer is within rail-excluded main shell; bottom:0 is not automatically rail overlap. Source review only; no rendered contrast, geometry, keyboard/device or visual certification. |
| [features/chat/views/SharedChatView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/chat/views/SharedChatView.vue>) | Active | No local finding | R1, R2, R4, R5, R7, R8 | Inspected token-change guards, loading/error states, document title restoration and shared transcript. A suspected late-response title issue was excluded: failure of the live route-token guard was not established. Navigation-away regression check remains pending. |
| [features/generator/GeneratorView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/generator/GeneratorView.vue>) | Active | [O12](#o12) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed request sequence and timer cleanup, result discard confirmation, draft options, named toggles/selectors, busy output and custom range CSS. O12 Firefox focus. Source-only inspection; no visual or device pass is implied. |
| [features/memory/MemoryView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/memory/MemoryView.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed cheap local search, pagination, save guard, retained errors/drafts, route/unload protection, delete confirmation and persistent editor layout; form-level server error is not assumed field validation. Source-only inspection; no visual or device pass is implied. |
| [features/notes/NotesView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/notes/NotesView.vue>) | Active | [O2](#o2), [O3](#o3) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed title/body/tags preservation, conflict recovery, Save controls, selection/route/unload discard protection, suggestion generations, delete confirmation and mobile dialogs outside hidden modes. Publication child issues O2/O3. Source-only inspection; no visual or device pass is implied. |
| [features/notes/components/NotePromotionPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/notes/components/NotePromotionPanel.vue>) | Active | [O2](#o2), [O3](#o3) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed review/suggest/publish async chains, source-version watcher, publication path/Markdown editing, shared audience toggle and dialog close behavior; O2/O3. Source-only inspection; no visual or device pass is implied. |
| [features/overview/OverviewView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/overview/OverviewView.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed genuine navigation links, access-gated cards, focus, mobile single column, decorative aria-hidden hero art. Decorative orbit is not auto-moving information; no pause requirement asserted for it. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/PdfMergerView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/PdfMergerView.vue>) | Active | [O15](#o15) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed account reset, store request stop on leave, source/page modes, output labels, shared dialogs and workspace.css scroll/mobile layout. O15 same panel-switching semantics as media modes. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/DropZone.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/DropZone.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed named role-button with Enter/Space and hidden native file picker, accepted types and parent-provided focus/hit area. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/MergeBar.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/MergeBar.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed canMerge guard, running/completed/error output, result download and in-app busy cancel confirmation; store generations and parent styles inspected. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/OutputPanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/OutputPanel.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed output metadata visible labels, number constraints, named shared exclusive selectors and toggle; token input and focus styles. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/PageStrip.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/PageStrip.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed page drag/reorder plus real earlier/later button alternatives and Alt arrow support; parent workspace.css supplies focus/mobile sizing. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/PageThumb.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/PageThumb.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed lazy IntersectionObserver setup/disconnect, PDF render failure fallback, decorative image alt and visible figcaption; no geometry-as-radius claim. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/SourceList.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/SourceList.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed reorder keyboard alternatives, drag state and in-app busy source-removal confirmation; deletion errors persist in parent notices through store errors. Source-only inspection; no visual or device pass is implied. |
| [features/pdfMerger/components/SourceRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/pdfMerger/components/SourceRow.vue>) | Active | [O5](#o5) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed range handling via store, image select, rotate, reorder buttons, danger zone and per-source confirmation parent. O5 live validation/missing field association. Source-only inspection; no visual or device pass is implied. |
| [features/settings/SettingsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/settings/SettingsView.vue>) | Active | [O14](#o14) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed draft/account guards, explicit Save/Revert, notifications permission, leave/unload handling, per-setting reset, local filtering and save-bar mobile anchoring. O14 policy mismatch. Source-only inspection; no visual or device pass is implied. |
| [features/settings/components/SidebarEditor.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/settings/components/SidebarEditor.vue>) | Active | [O9](#o9) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed drag plus keyboard-operable up/down alternatives, pin state, labeled visibility switch and draft emission; O9 actual28px width. Source-only inspection; no visual or device pass is implied. |
| [features/tickets/TicketsView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/tickets/TicketsView.vue>) | Active | [O1](#o1) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed local search, list/detail request generations, poll visibility/unmount cleanup, new/reply submission guards, confirmations and mobile forms. O1 confirmed reply loss; scoped status-filter min-height40px also merits touch follow-up. Source-only inspection; no visual or device pass is implied. |
| [features/usage/UsageView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/usage/UsageView.vue>) | Active | [O13](#o13) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed latestLoad guard, report-preserving refresh, grouping heading from loaded report, year data, table and export source/metadata. O13; runtime table overflow/contrast unverified. Source-only inspection; no visual or device pass is implied. |
| [features/usage/components/UsageCall.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/usage/components/UsageCall.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed token/provider/model row text, token CSS and long-label wrapping; tokens side is nonshrinking and needs rendered narrow-content verification. Source-only inspection; no visual or device pass is implied. |
| [features/videoDownloader/VideoDownloaderView.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/VideoDownloaderView.vue>) | Active | [O15](#o15) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed mounted/deactivated/route cleanup, account generation, v-show mode preservation, external file dialogs and confirmed file-delete/cancel flows; stores guard probe/file epochs and account changes. Panel semantics finding O15. Source-only inspection; no visual or device pass is implied. |
| [features/videoDownloader/components/FileRow.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/components/FileRow.vue>) | Active | [O10](#o10) | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed permission/expiry-aware download link, file details action and actual shared/scoped touch sizing; O10. Source-only inspection; no visual or device pass is implied. |
| [features/videoDownloader/components/JobCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/components/JobCard.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed status text, progress, elapsed timer child, busy cancel, completed-file fallback and dismiss behavior; parent confirms cancel. Source-only inspection; no visual or device pass is implied. |
| [features/videoDownloader/components/PackagePanel.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/components/PackagePanel.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed persistent per-group drafts, account reset, lifecycle watcher stops, failed-link retention and in-app start/remove confirmations; store epochs reject stale results. Source-only inspection; no visual or device pass is implied. |
| [features/videoDownloader/components/ProbeCard.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/components/ProbeCard.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed truthful unavailable preview, API formats/blocked reasons, busy-disabled download, named shared exclusive selector and responsive wrapping. Shared-selector semantics considered separately. Source-only inspection; no visual or device pass is implied. |
| [features/videoDownloader/components/UrlBar.vue](<D:/User/Documents/Programming/Python/Citadel/apps/Ember/ember_web/src/features/videoDownloader/components/UrlBar.vue>) | Active | No local finding | R1, R2, R3, R4, R5, R6, R7, R8, R9 | Reviewed URL input accessible name/type, submit emission, canCheck store guard, aria-busy and scoped styles. Visible heading supplied by parent; no automatic remote search or IME debounce applies. Source-only inspection; no visual or device pass is implied. |

## Suggested correction order

1. Bind chat edits to conversation identity (CHAT-01); address IME-triggered resend and attachment loss in the same focused chat review.
2. Guard asynchronous ownership and protect drafts in tool forms, note publication, templates, extension dialogs and ticket replies; fix chart shrink and report export identity.
3. Correct shared keyboard, form-error, progress and mobile hit-area behavior, coordinating duplicated Admin components.
4. Choose text-safe theme pairs and consolidate chart tokens; reconcile settings and panel-tab documentation.
5. Run targeted regressions and rendered/device checks against each corrected scenario before claiming compliance.

No production code, skills, Brain rule notes or tests were changed by this audit. The earlier redundancy inventory remains in COMPONENT_AUDIT.md; inactive files were inspected here without assuming they should be deleted.
