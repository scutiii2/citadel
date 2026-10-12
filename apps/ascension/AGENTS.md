# Ascension

The game (backend `src/`, web UI `web/`). The parent monorepo rules in `../../AGENTS.md` apply too.

## Where an Ascended's files live
Everything that belongs to one Ascended lives in its own folder, `ascended/<id>/`, next to its `catalog.json` and `tree.json` (ability nodes and graph positions).
Never put a file for a single Ascended in `web/src/assets` or any shared folder.

Sprites, per Ascended (exact names, WebP):
- `sprite_main_card.webp`: the art in the full card design.
- `sprite_preview_card.webp`: the small card (collection, shop offers, starter list).
- `sprite_battle.webp`: the fighter in the battle arena.

An Ascended may also hold `spreadsheet_animation.webp` (a grid of frames, one row per state, facing right) and
`animations.json` (the grid and each state's row, frame count, frame time and loop; the sheet rules are in `ascended/ART_GUIDE.md`, section 9). The battle arena plays it in place
of `sprite_battle.webp`; Ascended without one keep the still sprite.

Also in each folder: `art_prompts.md`, the visual canon of that Ascended and three ready-to-paste ChatGPT prompts
(main card, preview card, battle). The shared ruleset for all of them is `ascended/ART_GUIDE.md`: sizes, the pixel-art
style bible, the black battle background, the crop and convert commands and the checklist. Make or change sprites
with those, and change the prompts when the design changes.

The game serves them at `/ascended/<id>/<file>`; the web code never imports them. Shared card templates
(`ascended/ascended_common_*_template.png`) belong to no single Ascended and stay in `ascended/`.
`tests/ascension/test_ascended_layout.py` enforces the names and the folder.
