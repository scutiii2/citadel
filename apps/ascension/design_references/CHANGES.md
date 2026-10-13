# Ascension UI changes, 2026-10-13

Record of the UI edits made on `main` after `7a149df` (`feat(ascension): checkpoint UI redesign progress`),
up to `9cfa4c6`. `manifest.json` holds the SHA-256 of every file below as committed at `9cfa4c6`.
After merging another branch, run `python design_references/verify.py` from `apps/ascension/`.
A file reported `CHANGED` was edited by the merge: check that these changes survived.

Paths are relative to `apps/ascension/`.

## What changed and where

| Change | Files |
|---|---|
| Page header (eyebrow, title, subtitle) removed on every screen, starter screen included | `web/src/App.vue`, `web/src/App.test.ts` |
| Battle controls (Manual/Autonomous, Forfeit) are icon-only and sit above the round log in `.battle-side` | `web/src/App.vue`, `web/src/components/BattleControls.vue`, `web/src/components/ui/EmTabs.vue` (`iconOnly` prop), `web/src/components/BattlePanels.test.ts` |
| Ability tree: drag to pan, wheel to zoom at cursor, no scrollbar, icon-only controls and range slider above the map, nothing selectable | `web/src/components/TreeTab.vue`, `web/src/components/TreeTab.test.ts`, `web/src/components/ui/icons.ts` (`zoomIn`, `zoomOut`, `fit`, `eye`) |
| Ascended details dialog has a fixed size; preset list no longer swaps to "Loading …" when switching presets | `web/src/components/CollectionPanel.vue`, `web/src/components/PresetEditor.vue` |
| Main menu row hover flicker fixed (brightness filter instead of background swap) | `web/src/components/ui/EmMenuRow.vue` |
| Header "How to play" and "Settings" buttons removed; the ASCENSION logo is the button back to the main menu | `web/src/App.vue`, `web/src/App.test.ts` |
| Text selection disabled across the game UI (inputs exempt) | `web/src/components/theme.css` |
| Star cost shown as a list ("1 spare copy", "N essence", each with "You have X" and a green border when met) instead of a sentence | `web/src/components/CollectionPanel.vue`, `web/src/components/CollectionPanel.test.ts` |
| Fainted Ascended marked in the squad strip (greyed portrait, countdown) and on collected cards (red "Fainted" badge) | `web/src/components/CollectionPanel.vue`, `web/src/components/AscendedCard.vue` |
| Touch-first devices get an "Ascension is PC only" notice instead of the game | `web/src/App.vue`, `web/src/App.test.ts` |
| Squad can be emptied (server accepts 0 to N); an empty squad cannot battle (Fight disabled, caption says so) | `src/ascension/squad.py`, `tests/ascension/test_squad.py`, `web/src/components/CollectionPanel.vue`, `web/src/components/EncounterPanel.vue` |
| Squad slots lose their Remove button; help icon beside "Your squad" explains the squad and how to add or remove (new `info` icon) | `web/src/components/CollectionPanel.vue`, `web/src/components/ui/icons.ts` |
| Preview card frame and corner brackets take the tier colour; the tier label is replaced by `★ N` stars (new `stars` prop, shown where passed) beside the type symbols | `web/src/components/AscendedPreviewCard.vue`, `web/src/components/AscendedPreviewCard.test.ts`, `web/src/components/AscendedCard.vue` |
| Collection card is the bare preview card (no wrapper box, no name below it); only a fainted countdown shows under it | `web/src/components/AscendedCard.vue`, `web/src/components/CollectionPanel.test.ts` |
| Squad slots show the same preview card as the collected grid (same 136px sizing, greyed when fainted, countdown below) | `web/src/components/CollectionPanel.vue`, `web/src/components/CollectionPanel.test.ts` |
| Pressing a collected or squad card opens the Ascended details dialog straight away; the side inspector ("Selected Ascended", Open details, Remove from squad) is gone and the layout is two columns | `web/src/components/CollectionPanel.vue`, `web/src/components/CollectionPanel.test.ts`, `e2e/ascension.spec.ts`, `e2e/details.spec.ts` |
| Preview card shows HP, Power and Speed over the art (new `stats` prop, shared `ascendedStats` helper); art background is tinted with the tier colour | `web/src/components/AscendedPreviewCard.vue`, `web/src/components/AscendedPreviewCard.test.ts`, `web/src/utils/ascension.ts`, `web/src/components/AscendedCard.vue` |
| No selected outline on pressed cards; hover drops the ring and keeps the glow with a lift and 3% grow (new `.preview-lift` class) | `web/src/components/theme.css`, `web/src/components/AscendedCard.vue`, `web/src/components/CollectionPanel.vue` |
| Preview card frame: tier-tinted metal body, inner highlight line, diamond ornaments top and bottom, thicker corner brackets, rounded corners from the radius tokens | `web/src/components/AscendedPreviewCard.vue`, `web/src/components/theme.css` |
| Not collected cards are only the face-down preview card (no name, no hint, no wrapper), with the same hover lift | `web/src/components/CollectionPanel.vue`, `web/src/components/CollectionPanel.test.ts` |
| Starter screen uses the preview card (stars, level, stats) in a row with a single "Start with ..." button; the large template card and the "Your chosen starter" panel are removed | `web/src/components/StarterPick.vue`, `web/src/components/StarterPick.test.ts`, `web/src/App.test.ts` |
| Main menu cards and the wild encounter card show stars and stats; the Encounter squad picker uses preview cards (fainted ones greyed with a countdown). Remaining screens are listed in `TODO.md` | `web/src/components/MainMenu.vue`, `web/src/components/MainMenu.test.ts`, `web/src/components/EncounterPanel.vue`, `web/src/components/EncounterPanel.test.ts` |
| Battle preparation: wild opponent and your fighter are two preview cards side by side (new `wildMultiplier` prop), the squad options sit below them as bare preview cards, the Battle plan stays in a right column | `web/src/components/BattleMatchup.vue`, `web/src/components/BattleMatchup.test.ts`, `web/src/components/EncounterPanel.vue` |
| Picked card on the starter and battle preparation screens: no padding, no outline and no ring; it keeps a glow and a subtle vertical drift, hover rises, grows and blooms in the tier colour | `web/src/components/ui/EmPickCard.vue`, `web/src/components/StarterPick.test.ts` |
| Battle: Skip button, click-to-skip and `skip()` removed, so every round animation plays to the end | `web/src/components/BattleArena.vue`, `web/src/stores/playback.ts`, `web/src/stores/playback.test.ts` |
| Portrait battle (900px and below): the "Your move" bar sits above the round log | `web/src/App.vue` |

## Commits

- `b3c9227` drop page header, icon-only battle controls above round log
- `e54837a` pan and zoom ability tree with icon controls, no selection
- `2c44588` fixed-size details dialog, no flicker on preset switch
- `6a5c990` stop menu row hover flicker
- `9564c6d` drop header help/settings, logo links to main menu
- `b60619f` disable text selection across the game UI
- `f817e14` PC-only notice on touch-first devices
- `759a78a` empty squad allowed, fainted indicators, star cost list, squad help tooltip
- `aa18682` tier-coloured card frame with stars, slimmer collection caption, squad uses preview card
- `8a9e571` preview card everywhere it fits, details open on press, ornate rounded frame with stats
- `9cfa4c6` preview-card matchup and squad picker, glow-only pick animation, no skip, portrait move bar above log
