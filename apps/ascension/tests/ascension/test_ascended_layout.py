import json
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


def test_the_shipped_ascended_have_all_three_sprites():
    for name in ("bruiser", "channeler", "forbidden", "guardian", "scout", "sentinel", "striker"):
        assert {f.name for f in (ASCENDEDS_PATH / name).glob("sprite_*")} == SPRITES, name


def test_no_sprites_are_kept_outside_the_ascended_folders():
    assert not (PROJECT / "web" / "src" / "assets" / "ascended").exists()
    stray = [p for p in (PROJECT / "web" / "src").rglob("sprite_*")]
    assert stray == []


def test_every_ascended_has_its_art_prompts_and_the_shared_guide_exists():
    assert (ASCENDEDS_PATH / "ART_GUIDE.md").is_file()
    for folder in sorted(p for p in ASCENDEDS_PATH.iterdir() if (p / "catalog.json").is_file()):
        assert (folder / "art_prompts.md").is_file(), f"{folder.name} has no art_prompts.md"


def webp_size(path: Path) -> tuple[int, int]:
    """The pixel size of a WebP file, read from its header."""
    data = path.read_bytes()
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP", f"{path}: invalid WebP"
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset : offset + 4]
        length = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload = data[offset + 8 : offset + 8 + length]
        if kind == b"VP8X":
            return (1 + int.from_bytes(payload[4:7], "little"), 1 + int.from_bytes(payload[7:10], "little"))
        if kind == b"VP8L":
            assert payload[0] == 0x2F, f"{path}: invalid lossless WebP"
            bits = int.from_bytes(payload[1:5], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        if kind == b"VP8 ":
            assert payload[3:6] == bytes([0x9D, 0x01, 0x2A]), f"{path}: invalid WebP frame"
            return (int.from_bytes(payload[6:8], "little") & 0x3FFF, int.from_bytes(payload[8:10], "little") & 0x3FFF)
        offset += 8 + length + (length % 2)
    raise AssertionError(f"{path}: no image chunk")


def test_every_shipped_sprite_has_the_required_webp_dimensions():
    expected = {
        "sprite_main_card.webp": (1536, 796),
        "sprite_preview_card.webp": (512, 512),
        "sprite_battle.webp": (512, 512),
    }
    for path in sorted(ASCENDEDS_PATH.glob("*/sprite_*.webp")):
        assert webp_size(path) == expected[path.name], f"{path}: expected {expected[path.name]}"


def test_an_animation_sheet_is_a_grid_of_square_frames_described_by_its_json():
    sheets = sorted(ASCENDEDS_PATH.glob("*/spreadsheet_animation.webp"))
    assert sheets, "twoychi ships a sheet"
    for sheet in sheets:
        grid = json.loads((sheet.parent / "animations.json").read_text(encoding="utf-8"))
        width, height = webp_size(sheet)
        assert width % grid["columns"] == 0 and height % grid["rows"] == 0, f"{sheet}: not an even grid"
        assert width // grid["columns"] == height // grid["rows"], f"{sheet}: frames are not square"
