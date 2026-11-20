from src.brain.limits import LONG_TERM_RANGES, LongTermLimits, STACK_RANGES, brain_root, load_long_term
from src.citadel_auth import settings_store


def store(tmp_path, key, value):
    path = tmp_path / "settings.db"
    settings_store.put(path, "brain", key, value)
    return path


def test_defaults_match_the_spec(tmp_path):
    assert load_long_term(tmp_path / "missing.db") == LongTermLimits()
    limits = LongTermLimits()
    assert (limits.max_record_chars, limits.max_files, limits.max_total_bytes, limits.search_limit) == (20_000, 500, 5_000_000, 8)


def test_saved_values_are_clamped_and_unusable_ones_ignored(tmp_path):
    path = store(tmp_path, "long_term", {
        "max_record_chars": 10**9, "max_files": "many", "max_total_bytes": True, "search_limit": 0,
    })
    got = load_long_term(path)
    assert got.max_record_chars == LONG_TERM_RANGES["max_record_chars"][1] == 100_000
    assert got.max_files == 500 and got.max_total_bytes == 5_000_000
    assert got.search_limit == 1


def test_a_document_that_is_not_an_object_gives_the_defaults(tmp_path):
    assert load_long_term(store(tmp_path, "long_term", "oops")) == LongTermLimits()


def test_the_ranges_are_one_source(tmp_path):
    assert STACK_RANGES["max_items"] == (2, 200)
    assert set(LONG_TERM_RANGES) == {"max_record_chars", "max_files", "max_total_bytes", "search_limit"}


def test_the_root_is_the_environment_then_the_setting_then_the_data_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("STRONGHOLD_BRAIN_ROOT", raising=False)
    db = tmp_path / "settings.db"
    assert brain_root(tmp_path, db) == tmp_path / "brain"
    settings_store.put(db, "brain", "root", "   ")
    assert brain_root(tmp_path, db) == tmp_path / "brain"
    settings_store.put(db, "brain", "root", str(tmp_path / "elsewhere"))
    assert brain_root(tmp_path, db) == tmp_path / "elsewhere"
    monkeypatch.setenv("STRONGHOLD_BRAIN_ROOT", str(tmp_path / "env"))
    assert brain_root(tmp_path, db) == tmp_path / "env"
