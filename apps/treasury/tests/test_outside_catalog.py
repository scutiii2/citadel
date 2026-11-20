# apps/treasury/tests/test_outside_catalog.py
import sqlite3

import pytest

from src import outside_catalog as oc


@pytest.fixture
def db(tmp_path):
    return tmp_path / "settings.db"


@pytest.mark.parametrize("text, expected", [
    ("http://bard:29400", ("http://bard:29400", "")),
    ("HTTP://Bard:29400/mcp/", ("http://bard:29400", "/mcp")),
    ("http://bard:80/api", ("http://bard", "/api")),
    ("https://bard.lan:443", ("https://bard.lan", "")),
    ("http://[::1]:29400/x", ("http://[::1]:29400", "/x")),
])
def test_an_address_is_split_into_origin_and_path(text, expected):
    assert oc.split_origin(text) == expected


@pytest.mark.parametrize("text", [
    "", "bard:29400", "ftp://bard", "http://u:p@bard", "http://bard?x=1", "http://bard#f", "http://bard:0",
    "http://bard:abc", 'http://bad"host', "http://bad%host", "http://bad{host}", None, 5,
])
def test_a_bad_address_is_refused(text):
    with pytest.raises(oc.OutsideCatalogError):
        oc.split_origin(text)


def test_a_new_origin_needs_a_name_and_creates_a_group_with_ids(db):
    with pytest.raises(oc.OutsideCatalogError, match="give it a name"):
        oc.add_origin(db, "http://bard:29400", None, "legion")
    group = oc.add_origin(db, "http://bard:29400/mcp", "Bard", "legion")
    assert group["name"] == "bard" and group["used_by"] == ["legion"]
    assert len(group["service_id"]) == 32 and len(group["origins"][0]["origin_id"]) == 32
    assert group["origins"][0]["origin"] == "http://bard:29400"


def test_a_known_origin_returns_its_group_and_ignores_the_given_name(db):
    first = oc.add_origin(db, "http://bard:29400", "bard", "legion")
    again = oc.add_origin(db, "http://bard:29400/api", "other-name", "stronghold")
    assert again["service_id"] == first["service_id"] and again["name"] == "bard"
    assert again["used_by"] == ["legion", "stronghold"]
    assert len(again["origins"]) == 1


def test_an_existing_name_takes_the_new_origin_as_a_backup(db):
    first = oc.add_origin(db, "http://bard:29400", "bard", "legion")
    backup = oc.add_origin(db, "http://bard2:29400", "BARD", "legion")
    assert backup["service_id"] == first["service_id"]
    assert [o["origin"] for o in backup["origins"]] == ["http://bard2:29400", "http://bard:29400"]


@pytest.mark.parametrize("name", ["armory", "Treasury", "legion", "", " ", "bad name", "-x", "x" * 41])
def test_citadel_names_and_bad_names_are_refused(db, name):
    with pytest.raises(oc.OutsideCatalogError):
        oc.add_origin(db, "http://x:1", name, "legion")
    assert oc.view(db) == {"groups": []}


def test_rename_keeps_the_service_id_and_names_stay_unique(db):
    bard = oc.add_origin(db, "http://bard:1", "bard", "legion")
    oc.add_origin(db, "http://scribe:1", "scribe", "legion")
    renamed = oc.rename_group(db, bard["service_id"], "Speech")
    assert renamed["service_id"] == bard["service_id"] and renamed["name"] == "speech"
    with pytest.raises(oc.OutsideCatalogError):
        oc.rename_group(db, bard["service_id"], "scribe")
    with pytest.raises(oc.OutsideCatalogError):
        oc.rename_group(db, bard["service_id"], "armory")
    with pytest.raises(oc.NotFound):
        oc.rename_group(db, "0" * 32, "x")


def test_deleting_a_used_group_or_origin_needs_confirmation(db):
    group = oc.add_origin(db, "http://bard:1", "bard", "legion")
    origin_id = group["origins"][0]["origin_id"]
    with pytest.raises(oc.InUse) as error:
        oc.delete_origin(db, origin_id)
    assert error.value.users == ["legion"]
    with pytest.raises(oc.InUse):
        oc.delete_group(db, group["service_id"])
    oc.delete_origin(db, origin_id, confirm=True)
    assert oc.view(db)["groups"][0]["origins"] == []
    oc.delete_group(db, group["service_id"], confirm=True)
    assert oc.view(db) == {"groups": []}


def test_deleting_a_group_removes_its_origins_and_its_users(db):
    from src.citadel_auth import settings_store

    group = oc.add_origin(db, "http://bard:1", "bard", "legion")
    oc.delete_group(db, group["service_id"], confirm=True)
    assert settings_store.read_all(db, "outside_origins") == {}
    assert settings_store.read_all(db, "outside_users") == {}
    with pytest.raises(oc.NotFound):
        oc.delete_origin(db, "0" * 32)
    with pytest.raises(oc.NotFound):
        oc.delete_group(db, group["service_id"])

def test_a_failed_add_origin_rolls_back_the_group_and_origin(db):
    oc.view(db)
    with sqlite3.connect(db) as connection:
        connection.execute("""
            CREATE TRIGGER reject_registration BEFORE INSERT ON outside_users
            BEGIN SELECT RAISE(ABORT, 'registration failed'); END;
        """)
    with pytest.raises(sqlite3.IntegrityError, match="registration failed"):
        oc.add_origin(db, "http://bard:1", "bard", "legion")
    assert oc.view(db) == {"groups": []}


def test_lookup_finds_an_origin_with_its_group_and_path_and_records_nothing(db):
    group = oc.add_origin(db, "http://bard:29400", "bard", "legion")
    found = oc.lookup(db, "http://BARD:29400/mcp/")
    assert found["found"] is True and found["path"] == "/mcp"
    assert found["origin_id"] == group["origins"][0]["origin_id"] and found["group"]["name"] == "bard"
    missing = oc.lookup(db, "http://other:1/x")
    assert missing == {"found": False, "origin": "http://other:1", "path": "/x", "origin_id": None, "group": None}
    assert oc.view(db)["groups"][0]["used_by"] == ["legion"] and len(oc.view(db)["groups"]) == 1
    with pytest.raises(oc.OutsideCatalogError):
        oc.lookup(db, "nope")
