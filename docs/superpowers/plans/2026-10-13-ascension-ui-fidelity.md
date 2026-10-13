# Approved-design fidelity correction

**Goal:** Reproduce the approved reference screens, correcting the simplified checkpoint on main (`7a149df`). Keep the correction on `codex/ascension-ui-fidelity` in the existing worktree.

**References:** `apps/ascension/design_references/`. The latest menu is `ChatGPT Image Oct 13, 2026, 01_00_12 AM.png`; the Tavern reference stays future-only. Other sheets show starter, collection/details, skills/personality, shop, and battle/result.

## Binding requirements for the original correction

**Later revision:** User requested incorporating main’s `apps/ascension/design_references/CHANGES.md`. Its newer decisions supersede the original collection/details/starter/preparation/card/header behavior below.

- Recreate the actual visual composition: single framed masthead, steel panels, copper gradient controls, pixel display titles, thin slate outlines, ornamental steel/copper character frames, and appropriate pixel scenery. Do not preserve old header/title/dialog layouts simply to save implementation work.
- Preserve current battle sprites and current EMBLEM/type assets. Never regenerate characters, delete legacy sprites, or invent game rules. Real stats/stock/abilities replace illustrative values without changing the layout's hierarchy.
- No Continue. Quick Battle primary; Collection/Shop/Help secondary; Tavern locked and teased.
- Desktop collection uses category navigation/filter rail, three-column squad/grid area and selected inspector. Character details become an actual page with its own back header and three-panel overview rather than a generic dialog.
- Shop mode tabs belong in the shared header. Match the dense three-column catalog and purchase/sale basket proportions and selected quantity controls; retain safe batching/retries/account isolation.
- Starter: three full-height character choices with adjacent selected-character inspector. Encounter: opponent, fighter grid, plan inspector. Battle: two fighters across a stage, log to the right, action strip below. Results: captured/victory art, rewards, squad XP/personality details.
- Distinct backgrounds/card art must match the approved scenes. Generate missing non-character assets from the references; retain a clear view of original battle sprites.
- Check actual browser screenshots beside the references at 1440px and mobile. Do not claim an exact bitmap match: dynamic text and preserved artwork differ, but approved structure, ornament, typography and proportions must be restored.

## Execution

- [x] Root: finish checkpoint rebase/merge; shared shell, shop, image assets and integration.
- [x] Worker: main menu and ornamental portrait cards against approved menu/starter references.
- [x] Worker: collection grid/inspector, full-page details, progression/tree/preset structure.
- [x] Worker: starter, encounter, arena/action/log/result fidelity and updated browser fixtures/screenshots.
- [x] Verify unit suite/build; actual browser navigation/back behavior and responsive composition; independent functional and visual review.

Review focuses: no simplified card border substitute, no extra generic page-heading bands, visible purchase basket actions, accurate back navigation from details/active battles, retained capture animation and original assets.

## Verification and delivery

- Checkpoint 7a149df was rebased and merged into main. Main subsequently advanced with separate work; correction remains uncommitted on codex/ascension-ui-fidelity.
- Full isolated frontend run: 31 files, 261 tests passed. The final tree-fit correction was then verified with 17 TreeTab tests, including narrow-width and short-height regressions.
- Production build passed after the tree fix. Chrome browser checks: 13 passed across desktop, tablet and mobile, including buy/sell transactions, full-page details/back navigation, starter selection, battle, and results.
- Reviewed actual screenshots against the reference sheets. Corrected starter label overlap, selected mode tabs, primary attack styling, opponent HP color, and permanently visible progression controls.
- Independent review found one functional issue: Fit tree had an 85% lower bound. Removed that bound for the explicit Fit action and fit both dimensions; default zoom remains 100%. No other confirmed functional regression or major structural omission was reported.
- Only shared scenery/frame assets were added; character, EMBLEM and type artwork is preserved.
- Preview gallery: C:/Users/User/.codex/visualizations/2026/10/13/01a1334f-6fed-7142-ac9c-4afa6f7a709c/ascension-fidelity/index.html

Actual game content replaces illustrative reference values and abilities. Complex catalog trees retain their real dependency graphs; Fit tree shows the full graph and zoom/pan allow inspection. Screenshots use deterministic browser fixtures.

## Main changes incorporated

Source: main CHANGES.md, covering changes through9cfa4c6. Applied all documented behavior in this worktree, preserving batch shop safety and shared scenery.

- Cards: main tier-tinted rounded metal frame, highlights/corners/diamond ornaments, stats and stars, bare card wrappers, lift/glow and selected drift.
- Collection: same136px squad and collected cards, direct fixed-size details dialog, no side inspector/slotRemove, squadhelp, faint countdowns, face-down uncollected, starcost lists, empty squad allowed.
- Starter: preview card row with a single start button. Preparation: preview-card wild/fighter matchup above squad choices with battleplan to the right.
- Header: logo returns to menu; help/settings removed. Page headings remain absent. Touch-first notice and input-exempt text selection rules applied.
- Battle: icon-only controls above roundlog, noSkip API/button/click handler, portraitactions above log.
- Tree: drag pan, wheel zoom anchored to pointer, icon controls+range slider, scrollbar hidden; Fit uses both dimensions. Preset lists persist during requests.
- Menu hover uses brightness filter, retaining gradients.

Verification: fullfrontend267passed; backend squad31passed; productionbuildpassed; finalChrome12passed. Independent review checked documented requirements and identified the missed menuhover fix, now corrected. Original character/emblem/type files unchanged in the correction.

Ran design_references/verify.py:16of31files intentionally differ from main’s recorded bytes because fidelity styles, integration, and regression tests were retained. The manifest stays at its documented baseline; no hashes were rewritten.

Updated preview gallery: C:/Users/User/.codex/visualizations/2026/10/13/01a1334f-6fed-7142-ac9c-4afa6f7a709c/ascension-main-sync/index.html
