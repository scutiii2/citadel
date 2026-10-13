# Ascension UI changes, 2026-10-13

Record of the UI edits made on `main` after `7a149df` (`feat(ascension): checkpoint UI redesign progress`),
up to `aa18682`. `manifest.json` holds the SHA-256 of every file below as committed at `aa18682`.
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
| Collection card caption keeps only the name (and the fainted countdown); stars, tier badge, copies and XP bar removed from it | `web/src/components/AscendedCard.vue`, `web/src/components/CollectionPanel.test.ts` |
| Squad slots show the same preview card as the collected grid (same 136px sizing, greyed when fainted, countdown below) | `web/src/components/CollectionPanel.vue`, `web/src/components/CollectionPanel.test.ts` |

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
