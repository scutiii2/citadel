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
