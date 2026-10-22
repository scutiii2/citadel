# Ember component rules corrections

Implemented on 2026-10-22 against the findings in [COMPONENT_RULESET_AUDIT.md](COMPONENT_RULESET_AUDIT.md). The audit remains the historical baseline; its findings and line references describe the code before these corrections.

All 41 counted findings have code corrections. The excluded CHAT-12 hypothesis remains excluded. This records implementation and automated evidence; it does not certify every rendered state or physical device.

| Finding | Correction |
| --- | --- |
| CHAT-01 | Bind editing and confirmation to conversation/account identity and the original message. Retain separate conversation edit drafts and reject a changed source message. |
| CHAT-02 | Native, named selection buttons for conversation rows and search hits. |
| CHAT-03 | Keep remote search composition local until committed; handle explicit Enter and Escape. |
| CHAT-04 | Expand compact chat actions to 44px touch dimensions. |
| CHAT-05 | Require the folder name before deleting a populated folder; retain the empty-folder path. |
| CHAT-06 | Protect unsaved prompt edits with explicit Stay/Discard confirmation. |
| CHAT-07 | Keep pending prompt saves attached to their editor; prevent departure/new editing during saves and retain state across external close/reopen. |
| CHAT-08 | Apply generated titles by stable row identity only while the original description and title still match. |
| CHAT-09 | Ignore composing Enter in question editing. |
| CHAT-10 | Give the message textarea a stable accessible name. |
| CHAT-11 | Capture command status before clearing the composer so unsent attachments remain available. |
| CHAT-13 | Expose busy state and pending feedback on decisions and dialog submissions. |
| CHAT-14 | Move context category colors into both apps' global theme tokens. |
| S1 | Per-field request identity prevents older dependent-option replies from replacing current choices. |
| S2 | Per-upload identity guards both success and failure, including repeated filenames and teardown. |
| S3 | Add an accessible daily usage table alongside the heatmap. |
| S4 | Reuse clipboard recovery, show retry/failure feedback, and own feedback timers. |
| S5 | Expand shared button/link/close/reset/removal targets in both dimensions; preserve consumer variants. |
| S6 | Expand switch labels into touch targets while keeping their visual tracks compact. |
| S7 | Respect composition during tag entry. |
| S8 | Give controls instance-scoped IDs and associate errors/descriptions with invalid fields. |
| S9 | Give the command form dialog a programmatic name. |
| S10 | Clear invalid chart selections when bucket counts shrink and guard missing tooltip data. |
| S11 | Contain generated tables in a named, keyboard-reachable local scroller. |
| O1 | Preserve replies per ticket; protect unsent ticket/reply drafts on navigation and unload. |
| O2 | Reject stale publication review responses across note/source changes; guard related async completions. |
| O3 | Retain publication text/path across dialog close, note changes, suggestion changes and All notes/editor transitions. Refresh source review metadata before restoring retained edits. |
| O4 | Bind extension save completion/error/finalization to the current dialog session. |
| O5 | Validate page ranges on blur and associate errors with their input. |
| O6 | Validate password confirmation after editing; associate its error with the field. |
| O7 | Prevent repeated auth submissions and expose action-specific pending feedback. |
| O8 | Associate verification errors with the code field and announce authentication failures. |
| O9 | Keep sidebar icon targets 44px and prevent flex shrink in both apps. |
| O10 | Raise media file/link mobile targets to 44px. |
| O11 | Raise Brain search, breadcrumb and Back targets to 44px. |
| O12 | Preserve a browser-independent keyboard focus outline on generator ranges. |
| O13 | Export using the loaded report's range, even while a different range is pending or fails. |
| O14 | Browser preferences apply immediately. Account/server settings keep explicit Save/Revert and draft protection. Admin theme follows the same policy. |
| O15 | Add an opt-in shared tab mode with roles, panel relationships, roving focus and arrow/Home/End navigation; use it for media/PDF workspace panels. |
| O16 | Track resource-read pending state, guard repeated submissions and show pending feedback. |
| GLOBAL-01 | Use a text-safe light accent in both apps and the skill template; test primary labels and accent text against base and 12% tinted surfaces in both themes. |

Shared component corrections were applied to the corresponding Admin copies. Admin's side-modal layout and other app-specific behavior were retained. Existing value-picker segmented groups remain groups; the tab mode is opt-in for panel navigation. Shared busy buttons receive a token-based spinner alongside their pending labels.

The authoritative Ember skills now reference the moved layout/dialog/feature paths, distinguish value selectors from panel tabs, and carry the corrected theme token. Generated Claude skill copies were produced with `sync_skills.py`; the sync check passes. The historical Brain project inventory was not rewritten as part of code remediation.

## Verification

Final gate results:

| Check | Ember Web | Ember Admin |
| --- | --- | --- |
| TypeScript (`vue-tsc -b`) | Passed | Passed |
| Full unit suite | 2,121 passed, 164 files | 514 passed, 54 files |
| Full browser suite | 76 passed | 31 passed |
| Production build | Passed through final browser gate | Passed through final browser gate |

The final Notes changes also passed 10 focused browser cases. Diff whitespace and skill synchronization checks pass. Initial browser attempts could not reach loopback servers inside the sandbox (WinError 10013); final browser gates ran outside it. Initial Admin browser failures exposed stale navigation assertions and missing mock routes, which were corrected before the clean full run.

Regression tests cover the concrete state/data-loss scenarios, composition, associated errors, pending actions and report identity. Browser fixtures were updated for real account-menu navigation, panel tab roles, explicit populated-folder confirmation, validation timing and instant local preferences. The media test ignores only the expected HTTP 405 console resource message at the mock's optional MCP notification endpoint; other console/page errors still fail it.

Physical-device keyboard/rotation, screen-reader interaction, and exhaustive contrast on every blended/hover/focus surface remain manual checks. Existing responsive browser coverage exercises desktop, tablet and narrow widths and both themes; passing it does not replace these device checks.
