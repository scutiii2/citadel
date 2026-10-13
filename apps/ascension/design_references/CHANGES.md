# Ascension UI changes, 2026-10-13

Record of the UI edits made on `main` after `7a149df` (`feat(ascension): checkpoint UI redesign progress`),
up to `b60619f`. `manifest.json` holds the SHA-256 of every file below as committed at `b60619f`.
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

## Commits

- `b3c9227` drop page header, icon-only battle controls above round log
- `e54837a` pan and zoom ability tree with icon controls, no selection
- `2c44588` fixed-size details dialog, no flicker on preset switch
- `6a5c990` stop menu row hover flicker
- `9564c6d` drop header help/settings, logo links to main menu
- `b60619f` disable text selection across the game UI
