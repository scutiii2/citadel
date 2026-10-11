# Ascension

The game (backend `src/`, web UI `web/`). The parent monorepo rules in `../../AGENTS.md` apply too.

## Where an Ascended's files live
Everything that belongs to one Ascended lives in its own folder, `ascended/<id>/`, next to its `catalog.json`.
Never put a file for a single Ascended in `web/src/assets` or any shared folder.

Sprites, per Ascended (exact names, WebP):
- `sprite_main_card.webp`: the art in the full card design.
- `sprite_preview_card.webp`: the small card (collection, shop offers, starter list).
- `sprite_battle.webp`: the fighter in the battle arena.

The game serves them at `/ascended/<id>/<file>`; the web code never imports them. Shared card templates
(`ascended/ascended_common_*_template.png`) belong to no single Ascended and stay in `ascended/`.
`tests/ascension/test_ascended_layout.py` enforces the names and the folder.
