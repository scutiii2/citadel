from __future__ import annotations

from citadel_auth import settings_store


def test_documents_round_trip_per_table(tmp_path):
    db = tmp_path / "nested" / "settings.db"

    settings_store.put(db, "extensions", "bard", {"label": "Bard"})
    settings_store.put(db, "extensions", "bard", {"label": "Bard 2"})
    settings_store.put(db, "capabilities", "web", {"enabled": False})

    assert settings_store.read_all(db, "extensions") == {"bard": {"label": "Bard 2"}}
    assert settings_store.read_all(db, "capabilities") == {"web": {"enabled": False}}
    settings_store.delete(db, "extensions", "bard")
    settings_store.delete(db, "extensions", "bard")
    assert settings_store.read_all(db, "extensions") == {}


def test_a_missing_store_reads_empty_and_is_not_created(tmp_path):
    assert settings_store.read_all(tmp_path / "none.db", "settings") == {}
    assert not (tmp_path / "none.db").exists()
