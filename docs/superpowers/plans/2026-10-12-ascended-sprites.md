# Ascended Sprites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Ascended keeps three sprites (`sprite_main_card`, `sprite_preview_card`, `sprite_battle`) in its own folder next to `catalog.json`; the game backend serves them and the web UI uses the right one in each place.

**Architecture:** `Catalog.load` records which of the three fixed file names exist per folder (`ArtSpec`) and reads optional crop values from `catalog.json`. `/ascension/catalog` carries an `art` block with URLs. A public route `GET /ascended/{id}/{file}` serves the files by whitelist. The web drops its hard-coded list for `spriteFor(art, slot)`.

**Tech Stack:** Python 3.11 + FastAPI + pytest (`apps/ascension`, venv `.venv_ascension`); Vue 3 + TypeScript + Vitest (`apps/ascension/web`).

**Spec:** `docs/superpowers/specs/2026-10-12-ascended-sprites-design.md`

## Global Constraints

- Sprite file names are exactly `sprite_main_card.webp`, `sprite_preview_card.webp`, `sprite_battle.webp`, in `apps/ascension/ascended/<id>/`.
- Everything that belongs to one Ascended lives in `ascended/<id>/`; nothing for one Ascended in `web/src/assets` or a shared folder. `web/src/assets/ascended/` must not exist afterwards.
- Slot use: `AscendedTemplateCard` full = main card, `compact` = preview card; collection, starter list and shop offers = preview card; battle arena = battle. A missing slot falls back to the first existing of main, preview, battle, else the letter placeholder.
- `art` in `catalog.json` is optional and may only hold `focus` and `focus_preview`, numbers from 0 to 100 (default 50).
- The sprite route is public, answers only for catalog ids and the three exact names, never builds a path from request text, and sends `Cache-Control: no-cache`.
- Tests: from `apps/ascension` run `.venv_ascension\Scripts\python -m pytest`; from `apps/ascension/web` run `npx vitest run` and `npx vue-tsc --noEmit`.
- Commit only when the user says "commit".

---

## Phase A: Files, backend and the rule (commit 1)

### Task 1: Move the sprites, add crop values, write the rule and its test

**Files:**
- Move: `apps/ascension/web/src/assets/ascended/<id>.webp` to `apps/ascension/ascended/<id>/sprite_main_card.webp` for `channeler`, `forbidden`, `guardian`, `scout`, `sentinel`, `striker`; copy that file to `sprite_preview_card.webp` and `sprite_battle.webp` in the same folder
- Modify: `apps/ascension/ascended/<id>/catalog.json` for those six (add `"art"`)
- Create: `apps/ascension/AGENTS.md`, `apps/ascension/CLAUDE.md`
- Test: `apps/ascension/tests/ascension/test_ascended_layout.py`

**Interfaces:**
- Produces: the folder layout above and `"art": {"focus": N, "focus_preview": N}` in each catalog.json: guardian 21/50, scout 10/50, striker 10/50, sentinel 12/14, channeler 30/43, forbidden 18/29.

- [ ] **Step 1: Write the failing layout test**

Create `tests/ascension/test_ascended_layout.py`:

```python
from pathlib import Path

from tests.ascension.env import ASCENDEDS_PATH

SPRITES = {"sprite_main_card.webp", "sprite_preview_card.webp", "sprite_battle.webp"}
PROJECT = Path(__file__).resolve().parents[2]


def test_every_sprite_lives_in_its_ascended_folder_under_an_exact_name():
    for folder in sorted(p for p in ASCENDEDS_PATH.iterdir() if p.is_dir()):
        sprites = {f.name for f in folder.iterdir() if f.name.startswith("sprite_")}
        assert sprites <= SPRITES, f"{folder.name}: unexpected sprite files {sprites - SPRITES}"
        if sprites:
            assert (folder / "catalog.json").is_file(), f"{folder.name} has sprites but no catalog.json"


def test_the_shipped_ascended_have_all_three_sprites_except_bruiser():
    for name in ("channeler", "forbidden", "guardian", "scout", "sentinel", "striker"):
        assert {f.name for f in (ASCENDEDS_PATH / name).glob("sprite_*")} == SPRITES, name
    assert not list((ASCENDEDS_PATH / "bruiser").glob("sprite_*"))


def test_no_sprites_are_kept_outside_the_ascended_folders():
    assert not (PROJECT / "web" / "src" / "assets" / "ascended").exists()
    stray = [p for p in (PROJECT / "web" / "src").rglob("sprite_*")]
    assert stray == []
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_ascended_layout.py -q`
Expected: FAIL.

- [ ] **Step 2: Move and copy the files**

From `apps/ascension` (Git Bash), for each id in `channeler forbidden guardian scout sentinel striker`:

```bash
for id in channeler forbidden guardian scout sentinel striker; do
  git mv "web/src/assets/ascended/$id.webp" "ascended/$id/sprite_main_card.webp"
  cp "ascended/$id/sprite_main_card.webp" "ascended/$id/sprite_preview_card.webp"
  cp "ascended/$id/sprite_main_card.webp" "ascended/$id/sprite_battle.webp"
done
rmdir web/src/assets/ascended
```

- [ ] **Step 3: Add the crop values**

Add this key to each catalog.json right after `"name"`, with the values from the Interfaces list (guardian shown):

```json
 "art": { "focus": 21, "focus_preview": 50 },
```

- [ ] **Step 4: Write the rule**

Create `apps/ascension/AGENTS.md`:

```markdown
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
```

Create `apps/ascension/CLAUDE.md` containing exactly `@AGENTS.md`.

- [ ] **Step 5: Run**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_ascended_layout.py tests/ascension/test_catalog.py -q`
Expected: layout PASS. Catalog tests may fail on the unknown `art` key until Task 2; do not commit before Task 2 passes.

### Task 2: `ArtSpec`, discovery and validation

**Files:**
- Modify: `apps/ascension/src/ascension/catalog.py`
- Test: `apps/ascension/tests/ascension/test_catalog.py`

**Interfaces:**
- Produces: `SPRITE_NAMES = ("sprite_main_card.webp", "sprite_preview_card.webp", "sprite_battle.webp")`; `ArtSpec(main_card: bool, preview_card: bool, battle: bool, focus: float, focus_preview: float)`; `AscendedSpec.art: ArtSpec`; `Catalog.ascendeds_path: Path | None`; `Catalog.sprite_path(ascended_id: str, file: str) -> Path | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ascension/test_catalog.py`:

```python
def test_sprites_are_found_in_the_folder_and_crops_come_from_catalog_json(catalog):
    guardian = catalog.ascended("guardian").art
    assert (guardian.main_card, guardian.preview_card, guardian.battle) == (True, True, True)
    assert (guardian.focus, guardian.focus_preview) == (21, 50)
    assert catalog.ascended("sentinel").art.focus_preview == 14
    bruiser = catalog.ascended("bruiser").art
    assert (bruiser.main_card, bruiser.preview_card, bruiser.battle) == (False, False, False)
    assert (bruiser.focus, bruiser.focus_preview) == (50, 50)


def test_sprite_path_only_answers_for_catalog_ids_and_exact_names(catalog):
    assert catalog.sprite_path("guardian", "sprite_battle.webp").is_file()
    assert catalog.sprite_path("bruiser", "sprite_battle.webp") is None  # no such file
    assert catalog.sprite_path("nobody", "sprite_battle.webp") is None
    for bad in ("catalog.json", "../guardian/sprite_battle.webp", "sprite_battle.png", "SPRITE_BATTLE.WEBP", ""):
        assert catalog.sprite_path("guardian", bad) is None


def test_a_catalog_built_from_a_dict_has_no_sprites(raw):
    assert Catalog(copy.deepcopy(raw)).ascended("guardian").art.main_card is False


@pytest.mark.parametrize("art", [{"focus": 101}, {"focus": -1}, {"focus_preview": "x"}, {"focus": True}, {"other": 1}, "no"])
def test_a_bad_art_section_is_refused(raw, art):
    with pytest.raises(CatalogError, match="art"):
        Catalog(_broken(raw, lambda d: _ascended(d, "guardian").update(art=art)))
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_catalog.py -q`
Expected: FAIL.

- [ ] **Step 2: Implement**

In `catalog.py` add near the other constants `SPRITE_NAMES = ("sprite_main_card.webp", "sprite_preview_card.webp", "sprite_battle.webp")`. Add before `AscendedSpec`:

```python
@dataclass(frozen=True)
class ArtSpec:
    """Which sprites an Ascended's folder holds, and where to centre the crop (percent, like CSS object-position)."""

    main_card: bool = False
    preview_card: bool = False
    battle: bool = False
    focus: float = 50
    focus_preview: float = 50
```

Add `art: ArtSpec = ArtSpec()` as the last field of `AscendedSpec`. Add above `_ascended_spec`:

```python
def _art(raw: Mapping[str, Any], where: str) -> ArtSpec:
    art = raw.get("art", {})
    if not isinstance(art, Mapping) or set(art) - {"focus", "focus_preview"}:
        raise CatalogError(f"{where}: art may only set focus and focus_preview")
    focus = {}
    for key in ("focus", "focus_preview"):
        value = art.get(key, 50)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise CatalogError(f"{where}: art {key} must be a number from 0 to 100")
        focus[key] = value
    found = raw.get("sprites", [])
    return ArtSpec(*(name in found for name in SPRITE_NAMES), **focus)
```

and pass `art=_art(raw, where)` in the `AscendedSpec(...)` call in `_ascended_spec`. In `Catalog.__init__` set `self.ascendeds_path: Path | None = None` before `_build`. In `load` replace `return cls(raw)` with:

```python
        catalog = cls(raw)
        catalog.ascendeds_path = ascendeds_path
        return catalog
```

In `_load_ascendeds`, before `ascendeds.append(ascended)`, add:

```python
            ascended["sprites"] = [name for name in SPRITE_NAMES if (folder / name).is_file()]
```

Add the method to `Catalog`:

```python
    def sprite_path(self, ascended_id: str, file: str) -> Path | None:
        """The sprite file for a catalog Ascended and one of the three exact names, else None.
        The path is built from the catalog id and the fixed name, never from request text."""
        if self.ascendeds_path is None or file not in SPRITE_NAMES or ascended_id not in self._ascendeds:
            return None
        path = self.ascendeds_path / ascended_id / file
        return path if path.is_file() else None
```

- [ ] **Step 3: Run**

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension -q`
Expected: PASS.

### Task 3: Catalog answer and the sprite route

**Files:**
- Modify: `apps/ascension/src/ascension/api.py`, `apps/ascension/src/web.py`
- Test: `apps/ascension/tests/ascension/test_api.py`, `apps/ascension/tests/test_web.py`

**Interfaces:**
- Consumes: `Catalog.sprite_path`, `AscendedSpec.art`.
- Produces: per Ascended in `/ascension/catalog`: `art: {main_card, preview_card, battle, focus, focus_preview}` with URLs `"/ascended/<id>/<file>"` or `null`; public `GET /ascended/{ascended_id}/{file}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ascension/test_api.py`:

```python
def test_the_catalog_lists_each_ascended_s_sprites(client):
    data = client.get("/ascension/catalog", headers=headers(client, key=False)).json()
    by_id = {s["id"]: s for s in data["ascendeds"]}
    assert by_id["guardian"]["art"] == {
        "main_card": "/ascended/guardian/sprite_main_card.webp",
        "preview_card": "/ascended/guardian/sprite_preview_card.webp",
        "battle": "/ascended/guardian/sprite_battle.webp",
        "focus": 21, "focus_preview": 50,
    }
    assert by_id["bruiser"]["art"]["main_card"] is None and by_id["bruiser"]["art"]["battle"] is None


def test_sprites_are_public_and_never_stale(client):
    response = client.get("/ascended/guardian/sprite_battle.webp")
    assert response.status_code == 200 and response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "no-cache" and response.headers["etag"]
    assert response.content[:4] == b"RIFF"


@pytest.mark.parametrize("path", [
    "/ascended/nobody/sprite_battle.webp", "/ascended/bruiser/sprite_battle.webp", "/ascended/guardian/catalog.json",
    "/ascended/guardian/sprite_battle.png", "/ascended/guardian/%2e%2e/guardian/sprite_battle.webp",
    "/ascended/%2e%2e/configs/ascension_catalog.json", "/ascended/guardian/..%5ccatalog.json", "/ascended/guardian",
])
def test_any_other_sprite_request_is_a_404_not_a_page(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")
```

Run: `.venv_ascension\Scripts\python -m pytest tests/ascension/test_api.py -q -k "sprite or catalog_lists"`
Expected: FAIL.

- [ ] **Step 2: Implement**

In `api.py` import `FileResponse` from `fastapi.responses` and `SPRITE_NAMES` from `src.ascension.catalog`. In `catalog_summary`, add to each Ascended dict:

```python
             "art": _art_summary(s),
```

and above `catalog_summary`:

```python
def _art_summary(spec) -> dict[str, Any]:
    art = spec.art
    present = (art.main_card, art.preview_card, art.battle)
    urls = [f"/ascended/{spec.id}/{name}" if here else None for name, here in zip(SPRITE_NAMES, present)]
    return {"main_card": urls[0], "preview_card": urls[1], "battle": urls[2], "focus": art.focus, "focus_preview": art.focus_preview}
```

Add the router builder and use it in `mount_ascendeds`:

```python
def build_art_router(catalog: Catalog) -> APIRouter:
    """Public: an <img> cannot send the bearer, and the art is not secret. Only catalog ids and the three exact names answer."""
    router = APIRouter()
    headers = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}

    @router.get("/ascended/{ascended_id}/{file}")
    async def sprite(ascended_id: str, file: str):
        path = catalog.sprite_path(ascended_id, file)
        if path is None:
            raise HTTPException(404, "Not Found")
        return FileResponse(path, media_type="image/webp", headers=headers)

    return router
```

```python
def mount_ascendeds(app: FastAPI, services: AscendedServices) -> None:
    install_error_handlers(app)
    app.include_router(build_router(services))
    app.include_router(build_art_router(services.catalog))
```

(`HTTPException` is already imported in `api.py`; if it is Starlette's, use the same one the file uses.)

In `src/web.py` add `"ascended"` to the prefix tuple in `page()`: `("ascension", "ascended", "session", "health")`. Add a test to `tests/test_web.py` (copy its existing helper for building the app) asserting `GET /ascended/guardian` returns 404, not the SPA page.

- [ ] **Step 3: Run the whole backend suite**

Run: `.venv_ascension\Scripts\python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: README (backend part)**

In `apps/ascension/README.md` add a row `| GET /ascended/{id}/{file} | Public sprite files: sprite_main_card, sprite_preview_card, sprite_battle (.webp) |` to the endpoint table, and a short "Ascended files" section pointing at `AGENTS.md` for the folder rule and describing `art` (`focus`, `focus_preview`) in `catalog.json`.

- [ ] **Step 5: Commit boundary 1 (only when the user says "commit")**

```bash
git add apps/ascension/ascended apps/ascension/src apps/ascension/tests apps/ascension/AGENTS.md apps/ascension/CLAUDE.md apps/ascension/README.md
git add -u apps/ascension/web/src/assets
git commit -m "feat: Ascended sprites live in each Ascended's folder and the game serves them"
```

---

## Phase B: Web (commit 2)

### Task 4: Types, `spriteFor` and the components

**Files:**
- Modify: `apps/ascension/web/src/api/AscensionClient.ts`, `AscensionClient.fixtures.ts`
- Create: `apps/ascension/web/src/utils/sprites.ts`, `apps/ascension/web/src/utils/sprites.test.ts`
- Delete: `apps/ascension/web/src/components/ascendedArt.ts`, `ascendedArt.test.ts`
- Modify: `components/AscendedTemplateCard.vue`, `components/BattleArena.vue`, `components/ShopPanel.vue`, their tests, `apps/ascension/web/vite.config.ts`, `apps/ascension/web/README.md`

**Interfaces:**
- Produces: `AscendedArtInfo { main_card: string | null; preview_card: string | null; battle: string | null; focus: number; focus_preview: number }`; `AscendedInfo.art: AscendedArtInfo`; `SpriteSlot = "main_card" | "preview_card" | "battle"`; `spriteFor(art: AscendedArtInfo | undefined, slot: SpriteSlot): string | null`; `spriteFocus(art: AscendedArtInfo | undefined, slot: SpriteSlot): number`.

- [ ] **Step 1: Write the failing tests**

Create `src/utils/sprites.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AscendedArtInfo } from "../api/AscensionClient";
import { spriteFocus, spriteFor } from "./sprites";

const ART: AscendedArtInfo = { main_card: "/a/main.webp", preview_card: "/a/preview.webp", battle: "/a/battle.webp", focus: 21, focus_preview: 50 };

describe("spriteFor", () => {
  it("gives the slot's own sprite", () => {
    expect(spriteFor(ART, "main_card")).toBe("/a/main.webp");
    expect(spriteFor(ART, "preview_card")).toBe("/a/preview.webp");
    expect(spriteFor(ART, "battle")).toBe("/a/battle.webp");
  });

  it("falls back to the first sprite that exists, in the order main, preview, battle", () => {
    expect(spriteFor({ ...ART, battle: null }, "battle")).toBe("/a/main.webp");
    expect(spriteFor({ ...ART, main_card: null, battle: null }, "battle")).toBe("/a/preview.webp");
    expect(spriteFor({ ...ART, main_card: null, preview_card: null }, "main_card")).toBe("/a/battle.webp");
  });

  it("is null when there is no sprite at all or no art", () => {
    expect(spriteFor({ ...ART, main_card: null, preview_card: null, battle: null }, "battle")).toBeNull();
    expect(spriteFor(undefined, "battle")).toBeNull();
  });
});

describe("spriteFocus", () => {
  it("uses focus for the main card, focus_preview for the preview card, 50 when unknown", () => {
    expect(spriteFocus({ ...ART, focus: 21, focus_preview: 14 }, "main_card")).toBe(21);
    expect(spriteFocus({ ...ART, focus: 21, focus_preview: 14 }, "preview_card")).toBe(14);
    expect(spriteFocus(undefined, "main_card")).toBe(50);
  });
});
```

Run: `npx vitest run src/utils/sprites.test.ts` from `apps/ascension/web`. Expected: FAIL (module missing).

- [ ] **Step 2: Types and helper**

In `AscensionClient.ts` add above `AscendedInfo` and add the field `art: AscendedArtInfo;` as the last member of `AscendedInfo`:

```ts
export interface AscendedArtInfo {
  main_card: string | null;
  preview_card: string | null;
  battle: string | null;
  /** Vertical crop centre, 0 to 100 (CSS object-position), for the main card and the preview card. */
  focus: number;
  focus_preview: number;
}
```

Create `src/utils/sprites.ts`:

```ts
import type { AscendedArtInfo } from "../api/AscensionClient";

export type SpriteSlot = "main_card" | "preview_card" | "battle";

const FALLBACK_ORDER: SpriteSlot[] = ["main_card", "preview_card", "battle"];

/** The picture for a slot: its own sprite, else the first one that exists, else null (the letter placeholder). */
export function spriteFor(art: AscendedArtInfo | undefined, slot: SpriteSlot): string | null {
  if (!art) return null;
  return art[slot] ?? FALLBACK_ORDER.map((name) => art[name]).find((url) => url !== null) ?? null;
}

/** Where to centre the crop for a slot, in percent. */
export function spriteFocus(art: AscendedArtInfo | undefined, slot: SpriteSlot): number {
  return (slot === "preview_card" ? art?.focus_preview : art?.focus) ?? 50;
}
```

- [ ] **Step 3: Fixtures**

In `AscensionClient.fixtures.ts`, add above `ascendedInfo` (the focus values are the shipped ones):

```ts
const SHIPPED_FOCUS: Record<string, [number, number]> = {
  guardian: [21, 50], scout: [10, 50], striker: [10, 50], sentinel: [12, 14], channeler: [30, 43], forbidden: [18, 29],
};

/** The art block the game sends: the six shipped Ascended have all three sprites, the others none. */
export function artFor(id: string): AscendedArtInfo {
  const focus = SHIPPED_FOCUS[id];
  const url = (name: string) => (focus ? `/ascended/${id}/sprite_${name}.webp` : null);
  return { main_card: url("main_card"), preview_card: url("preview_card"), battle: url("battle"), focus: focus?.[0] ?? 50, focus_preview: focus?.[1] ?? 50 };
}
```

import `AscendedArtInfo` in the type import, and add `art: artFor(id),` to the object `ascendedInfo` returns (before `...extra`).

- [ ] **Step 4: Components**

`AscendedTemplateCard.vue`: remove `import { ascendedArt } from "./ascendedArt";`, add `import { spriteFocus, spriteFor, type SpriteSlot } from "../utils/sprites";`, and replace lines 102 and 103 with:

```ts
const slot = computed<SpriteSlot>(() => (props.compact ? "preview_card" : "main_card"));
const artUrl = computed(() => spriteFor(props.ascended.art, slot.value));
const artPosition = computed(() => `50% ${spriteFocus(props.ascended.art, slot.value)}%`);
```

In the template change `<img v-if="art" class="portrait" :src="art.url"` to `<img v-if="artUrl" class="portrait" :src="artUrl"`. Update the comment that mentions `ascendedArt.ts` to say the Ascended's own sprite.

`BattleArena.vue`: remove the `ascendedArt` import, add `import { spriteFor } from "../utils/sprites";` and `import { useAscensionStore } from "../stores/ascension";`, add `const ascension = useAscensionStore();` and replace `art()` with:

```ts
function art(fighter: Fighter): string | null {
  const info = ascension.catalog?.ascendeds.find((a) => a.id === fighter.ascended_id);
  return spriteFor(info?.art, "battle");
}
```

`ShopPanel.vue`: replace the `ascendedArt` import with `import { spriteFor } from "../utils/sprites";` and `artOf` with:

```ts
const artOf = (id: string) => spriteFor(store.catalog?.ascendeds.find((a) => a.id === id)?.art, "preview_card");
```

Delete `ascendedArt.ts` and `ascendedArt.test.ts`.

In `vite.config.ts` add `'/ascended'` to the proxy list (`['/ascension', '/ascended', '/session', '/health']`).

- [ ] **Step 5: Run and fix the tests**

Run: `npx vitest run` and `npx vue-tsc --noEmit`.
Expected: PASS. `AscendedTemplateCard.test.ts` keeps working because the fixtures carry the shipped focus values (guardian main 21, sentinel preview 14); a test that mounts `BattleArena` or `ShopPanel` needs `store.catalog` set (they already set `CATALOG`). Add assertions: the large card uses the `main_card` URL and the compact one the `preview_card` URL (`img.portrait` `src` ends with `sprite_main_card.webp` and `sprite_preview_card.webp`), and the battle arena image ends with `sprite_battle.webp`.

- [ ] **Step 6: README and build**

In `web/README.md` add a short "Sprites" section: the game serves them from `ascended/<id>/`, `spriteFor` picks the slot and falls back, the dev proxy forwards `/ascended`. Remove any text that mentions `assets/ascended`. Run `npm run build` and confirm no `.webp` portraits are bundled from `src/assets/ascended`.

- [ ] **Step 7: Commit boundary 2 (only when the user says "commit")**

```bash
git add apps/ascension/web
git commit -m "feat: the web UI uses each Ascended's own sprites from the game"
```

---

## Self-review

- **Spec coverage:** layout and migration (Task 1), rule and its test (Task 1), discovery, `art` validation, `sprite_path` (Task 2), catalog `art` block, public route, headers, 404-not-SPA (Task 3), slot use, fallback, placeholder, dev proxy (Task 4), README updates (Tasks 3 and 4). The two-commit rollout is Phases A and B; Phase A deletes the old asset folder, which breaks the web build until Phase B lands, as the spec warns.
- **Placeholders:** none. Steps that depend on an existing test helper (the `tests/test_web.py` addition) say to copy that file's existing setup.
- **Type consistency:** `ArtSpec` fields and `SPRITE_NAMES` order match `_art_summary` (main, preview, battle); `AscendedArtInfo` matches the JSON keys; `spriteFor` and `spriteFocus` slot names match `SpriteSlot`.
