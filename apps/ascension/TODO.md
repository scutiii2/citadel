# Ascension TODO

## Use the collection preview card everywhere it applies

Done: Collection grid, squad strip, not-collected cards, starter screen, main menu hand, wild encounter card, Encounter squad picker.

Open (each one changes its screen layout, so do them one at a time and agree the layout first):

- [ ] Shop offers (`web/src/components/ShopPanel.vue`): own card layout with sprite, price and quantity controls. The preview card has to fit around the buy controls.
- [ ] Battle result (`web/src/components/BattleResult.vue`): large featured sprite plus text. Replace with the preview card.
- [ ] Ascended details dialog and ability tree (`web/src/components/CollectionPanel.vue`, `web/src/components/TreeTab.vue`): plain portrait; the side column is built around it.

Stays as it is: Battle arena and matchup (live fighter sprites, health bars and animation).

## Cleanup

- [ ] `web/src/components/AscendedTemplateCard.vue` is no longer used by the starter screen. Delete it (and its test) if nothing else needs it.
- [ ] Record the recent UI changes in `design_references/CHANGES.md` and re-run `python design_references/verify.py --update`.
