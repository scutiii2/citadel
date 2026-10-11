# Ascended sprites live in each Ascended's folder

Today the six portraits are `apps/ascension/web/src/assets/ascended/<id>.webp`, imported by name in
`web/src/components/ascendedArt.ts`, with the crop positions hard-coded there. One image serves the large
card, the small card and the battle arena. This design moves everything that belongs to one Ascended into its
own folder, adds a separate sprite for each use, and lets the game backend serve them, so adding an Ascended is
dropping a folder.

## Scope

1. Files: three sprites per Ascended, next to its `catalog.json`.
2. Backend (`apps/ascension`): discover the sprites, describe them in the catalog answer, serve them.
3. Web (`apps/ascension/web`): use the sprite that fits each place, drop the hard-coded list.
4. A written rule, enforced by a test, that everything belonging to one Ascended lives in its folder.

Out of scope: new artwork (the existing portrait is copied to all three names), other per-Ascended assets such
as sounds (the rule covers them when they come), Bruiser's art, the shared card templates, any change to ember_*.

## Decisions

| Question | Choice |
|---|---|
| How the web gets the images | The game backend serves them from the Ascended folders (not a build-time import) |
| What decides which sprites exist | The files found in the folder, not a list in `catalog.json` |
| Where the crop positions live | `catalog.json`, in an optional `art` object |
| A missing sprite | Falls back to the first one that exists (main, preview, battle), else the letter placeholder |

## Files

```
apps/ascension/ascended/<id>/
  catalog.json
  sprite_main_card.webp      art in the full card design
  sprite_preview_card.webp   small card (collection, shop offers, starter list)
  sprite_battle.webp         the fighter in the battle arena
```

- `apps/ascension/ascended/ascended_common_front_template.png` and `..._back_template.png` stay where they are:
  they belong to no single Ascended.
- Migration: each `web/src/assets/ascended/<id>.webp` (channeler, forbidden, guardian, scout, sentinel, striker)
  moves with `git mv` to `ascended/<id>/sprite_main_card.webp` and is copied to the other two names. Bruiser
  gets none. `web/src/assets/ascended/` is deleted.
- `ascended/spark_example/` is an empty leftover folder and is not touched.

## Backend

- `Catalog.load` already reads each `ascended/<id>/catalog.json`. It also checks which of the three exact file
  names exist in that folder and records them on the `AscendedSpec` as `art`:
  `ArtSpec(main_card: bool, preview_card: bool, battle: bool, focus: float = 50, focus_preview: float = 50)`.
  A catalog built from a raw dict (tests) has no folder and gets no sprites.
- `catalog.json` accepts an optional `"art": {"focus": 0 to 100, "focus_preview": 0 to 100}`; other keys under
  `art` or values outside the range are a `CatalogError`.
- `GET /ascension/catalog` gives each Ascended `art: { main_card, preview_card, battle, focus, focus_preview }`
  where the first three are `"/ascended/<id>/<file>"` or `null`.
- New public route `GET /ascended/{id}/{file}`, registered before the UI catch-all, no bearer needed (an `<img>`
  cannot send one, and the art is not secret):
  - 404 unless `id` is a catalog id and `file` is exactly one of the three names and the file exists;
  - the path is built from the catalog id and the fixed name, never from the request text, so `..`, backslashes
    and encoded forms cannot reach other files;
  - `Content-Type: image/webp`, `Cache-Control: no-cache` with the file's `ETag` and `Last-Modified` (replaced art
    shows after a reload and never goes stale), plus the same security headers as the UI.
- The page catch-all must keep answering 404 for `/ascended/...` paths it does not serve, not the SPA page.

## Web

- `AscendedInfo` gains `art` (the block above). `ascendedArt.ts` and `ascendedArt.test.ts` are replaced by a small
  `spriteFor(art, slot)` helper: it returns the URL for a slot, or the first existing of main, preview, battle, or
  `null`; the card focus is `art.focus` for the main slot and `art.focus_preview` for the preview slot.
- Which sprite each place uses:
  - `AscendedTemplateCard`: `main_card` normally, `preview_card` when `compact`;
  - collection and starter list (compact cards) and shop offer portraits: `preview_card`;
  - `BattleArena`: `battle`.
- A `null` result keeps the existing letter placeholder.
- The Vite dev proxy forwards `/ascended` to the game backend like `/ascension`.

## The rule

Written into `apps/ascension/AGENTS.md` (created if missing; `CLAUDE.md` imports it) and the README: every file
that belongs to one Ascended, such as sprites, and in future sounds or notes, lives in `ascended/<id>/`. Nothing
for a single Ascended goes in `web/src/assets` or a shared folder. A test enforces the part it can:

- every folder under `ascended/` that holds sprites also holds a `catalog.json`;
- every `sprite_*` file has one of the three exact names and the `.webp` extension;
- `web/src/assets/ascended/` does not exist.

## Testing

- Pytest: sprite discovery (present and missing), the `art` values and their validation, the `art` block in the
  catalog answer, the route (each file, unknown id, another file name, traversal and encoded traversal, headers,
  a 404 and not the SPA for `/ascended/...`), and the layout rule.
- Vitest: `spriteFor` (slot, fallback order, none), each component using its slot, the placeholder.
- Manual check by the user.

## Rollout, two commits

1. Backend: file moves and copies, catalog `art`, the route, the layout test, the rule in `AGENTS.md` and the README.
2. Web: `AscendedInfo.art`, `spriteFor`, components, the dev proxy, tests, README.

Between the two commits the web UI still imports `web/src/assets/ascended`, which commit 1 deletes, so do them
back to back.

## Risks

- Existing UI builds break if the assets folder is deleted before the web change lands: hence back to back.
- A public image route is a new unauthenticated path: it only serves three fixed names for catalog ids.
- Player-visible art does not change until you replace the copies with new art.
