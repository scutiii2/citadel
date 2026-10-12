import copy

import pytest

from src.ascension.catalog import Catalog, CatalogError
from tests.ascension.env import CATALOG_PATH, ASCENDEDS_PATH, load_raw


def _ascended(d, ascended_id):
    return next(s for s in d["ascendeds"] if s["id"] == ascended_id)


@pytest.fixture(scope="module")
def raw():
    return load_raw()


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load(CATALOG_PATH, ASCENDEDS_PATH)


def test_shipped_catalog_is_valid(catalog):
    assert catalog.version == 1
    assert [t.id for t in catalog.tiers] == ["common", "rare", "unique", "royal", "legendary", "forbidden"]
    assert len(catalog.all_ascendeds()) == 8
    assert [s.id for s in catalog.starter_ascendeds()] == ["guardian", "scout", "striker"]  # file-name order
    assert catalog.forbidden_ascended().id == "forbidden"
    assert len(catalog.regular_ascendeds()) == 7
    assert [s.id for s in catalog.all_ascendeds()] == ["bruiser", "channeler", "forbidden", "guardian", "scout", "sentinel", "striker", "twoychi"]


def test_stats_use_growth_then_tier_multiplier_and_floor(catalog):
    assert catalog.stat_value("guardian", 1, "common", "hp") == 150
    assert catalog.stat_value("guardian", 11, "common", "hp") == 300  # 150 + 15 * 10
    assert catalog.stat_value("scout", 3, "rare", "power") == 33  # (22 + 2.2 * 2) * 1.25 = 33.0
    assert catalog.stat_value("forbidden", 1, "forbidden", "hp") == 800
    assert catalog.stat_value("forbidden", 1, "forbidden", "speed") == 120
    assert catalog.stat_value("scout", 2, "common", "speed") == 38  # 35 + 3.5 = 38.5 floored


def test_every_ascended_grows_ten_percent_of_base(catalog):
    for spec in catalog.all_ascendeds():
        for stat in ("hp", "power", "speed"):
            assert spec.growth[stat] == pytest.approx(spec.base[stat] * 0.1)


@pytest.mark.parametrize("tier,stars,essence", [
    ("common", 1, 1), ("rare", 2, 2), ("unique", 3, 3), ("royal", 5, 4), ("legendary", None, 5), ("forbidden", None, 10),
])
def test_the_star_ladder_follows_the_unity_tiers(catalog, tier, stars, essence):
    assert (catalog.tier(tier).stars_to_advance, catalog.tier(tier).essence_cost) == (stars, essence)


def test_the_tier_above_follows_the_ladder_and_stops_at_legendary(catalog):
    assert [catalog.next_tier(t) for t in ("common", "rare", "unique", "royal", "legendary")] == [
        "rare", "unique", "royal", "legendary", None]


def test_an_owned_ascended_is_at_its_saved_tier_else_its_start_tier(catalog):
    assert catalog.start_tier("sentinel") == "common"
    assert catalog.tier_of("sentinel", None) == "common" and catalog.tier_of("sentinel", "royal") == "royal"


def test_forbidden_is_always_forbidden(catalog):
    assert catalog.start_tier("forbidden") == "forbidden"
    assert catalog.tier_of("forbidden", None) == "forbidden" and catalog.tier_of("forbidden", "common") == "forbidden"


def test_level_caps(catalog):
    assert catalog.level_cap("guardian") == 30 and catalog.level_cap("forbidden") == 50


def test_sale_value_formula(catalog):
    assert catalog.sale_value("guardian", "common", 1) == 100
    assert catalog.sale_value("guardian", "rare", 11) == 187  # 100 * 1.25 * 1.5 = 187.5
    assert catalog.sale_value("forbidden", "forbidden", 1) == 4000


def _broken(raw, mutate):
    data = copy.deepcopy(raw)
    mutate(data)
    return data


@pytest.mark.parametrize("mutate,message", [
    (lambda d: d["tiers"][0].update(encounter_probability=0.5), "sum to 1"),
    (lambda d: d["tiers"][1].update(id="common"), "unique"),
    (lambda d: d["tiers"][2].update(stars_to_advance=0), "stars_to_advance of at least 1"),
    (lambda d: d["tiers"][4].update(stars_to_advance=3), "the last needs null"),
    (lambda d: d["tiers"][1].update(essence_cost=0), "essence_cost of at least 1"),
    (lambda d: _ascended(d, "guardian").update(start_tier="forbidden"), "start_tier must be a regular tier"),
    (lambda d: _ascended(d, "guardian").update(starter=False), "three Ascended must be starters"),
    (lambda d: _ascended(d, "sentinel")["abilities"].pop(), "unlock at levels"),
    (lambda d: _ascended(d, "guardian")["abilities"][1].pop("duration"), "SUPPORT needs"),
    (lambda d: _ascended(d, "guardian")["abilities"][0].update(category="HEAL"), "category must be"),
    (lambda d: d["personalities"][0].update(categories=["NOPE"]), "invalid categories"),
    (lambda d: d["policy"]["coefficients"].pop("FEAR"), "coefficients missing"),
    (lambda d: _ascended(d, "guardian")["base"].pop("hp"), "exactly hp, power and speed"),
])
def test_inconsistent_catalogs_are_rejected(raw, mutate, message):
    with pytest.raises(CatalogError, match=message):
        Catalog(_broken(raw, mutate))


def test_unreadable_file_is_a_catalog_error(tmp_path):
    with pytest.raises(CatalogError, match="cannot load"):
        Catalog.load(tmp_path / "missing.json", ASCENDEDS_PATH)


def test_the_default_locations_load_the_shipped_catalog():
    assert [s.id for s in Catalog.load().all_ascendeds()] == [s.id for s in Catalog.load(CATALOG_PATH, ASCENDEDS_PATH).all_ascendeds()]


def test_the_shop_section_covers_the_regular_tiers(catalog):
    assert set(catalog.shop.stock) == {t.id for t in catalog.regular_tiers}
    assert set(catalog.shop.tier_weights) == set(catalog.shop.stock)
    assert catalog.shop.stock["common"] == 3 and catalog.shop.stock["legendary"] == 1


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("shop"),
    lambda d: d["shop"]["stock"].pop("rare"),
    lambda d: d["shop"]["stock"].update(common=0),
    lambda d: d["shop"]["tier_weights"].update(common=0),
    lambda d: d["shop"]["stock"].update(forbidden=1),
])
def test_a_bad_shop_section_is_refused(raw, mutate):
    with pytest.raises(CatalogError):
        Catalog(_broken(raw, mutate))


def test_sprites_are_found_in_the_folder_and_crops_come_from_catalog_json(catalog):
    guardian = catalog.ascended("guardian").art
    assert (guardian.main_card, guardian.preview_card, guardian.battle) == (True, True, True)
    assert (guardian.focus, guardian.focus_preview) == (21, 50)
    assert catalog.ascended("sentinel").art.focus_preview == 14
    bruiser = catalog.ascended("bruiser").art
    assert (bruiser.main_card, bruiser.preview_card, bruiser.battle) == (False, False, False)
    assert (bruiser.focus, bruiser.focus_preview) == (50, 50)


def test_a_sheet_in_the_folder_gives_a_checked_animation(catalog):
    animation = catalog.ascended("twoychi").art.animation
    assert set(animation["states"]) == {"idle", "attack", "defend", "support", "flee", "catch"}
    assert animation["states"]["idle"] == {"row": 0, "frames": 4, "frame_ms": 180, "loop": True}
    assert catalog.ascended("guardian").art.animation is None
    assert catalog.sprite_path("twoychi", "spreadsheet_animation.webp").is_file()
    assert catalog.sprite_path("guardian", "spreadsheet_animation.webp") is None


@pytest.mark.parametrize("animation", [
    "no", {}, {"columns": 4, "rows": 6, "states": {}},
    {"columns": 4, "rows": 1, "states": {"idle": {"row": 1, "frames": 4, "frame_ms": 100, "loop": True}}},
    {"columns": 4, "rows": 1, "states": {"idle": {"row": 0, "frames": 5, "frame_ms": 100, "loop": True}}},
    {"columns": 4, "rows": 1, "states": {"idle": {"row": 0, "frames": 4, "frame_ms": 0, "loop": True}}},
    {"columns": 4, "rows": 1, "states": {"idle": {"row": 0, "frames": 4, "frame_ms": 100, "loop": 1}}},
    {"columns": 4, "rows": 2, "states": {"idle": {"row": 0, "frames": 4, "frame_ms": 100, "loop": True},
                                         "dance": {"row": 1, "frames": 4, "frame_ms": 100, "loop": True}}},
])
def test_a_bad_animation_is_refused(raw, animation):
    with pytest.raises(CatalogError):
        Catalog(_broken(raw, lambda d: d["ascendeds"][0].update(animation=animation)))


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
