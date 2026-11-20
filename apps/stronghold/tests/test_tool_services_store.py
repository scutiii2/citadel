from src.tool_services.store import REQUIRED, ToolStore, ready_status, token_for, view


def test_an_unconfigured_service_is_not_ready_and_says_what_to_do(tmp_path):
    store = ToolStore(tmp_path / "settings.db")
    assert store.get("bard") == {"enabled": True, "service_id": None, "origins": [], "token": ""}
    assert ready_status("bard", store.get("bard")) == {"ready": False, "reason": "Configure Bard in Stronghold Admin."}
    assert set(store.records()) == set(REQUIRED)


def test_ready_needs_an_origin_and_a_token_for_every_origin_and_not_disabled():
    record = {"enabled": True, "service_id": "s", "origins": [{"origin_id": "o1"}], "token": ""}
    assert ready_status("scribe", record)["reason"] == "Set the Scribe token in Stronghold Admin."
    assert ready_status("scribe", {**record, "token": "t"}) == {"ready": True, "reason": None}
    both = {**record, "origins": [{"origin_id": "o1", "header_value": "a"}, {"origin_id": "o2"}]}
    assert ready_status("scribe", both)["ready"] is False            # o2 has no token of its own and there is no parent
    assert ready_status("scribe", {**record, "token": "t", "enabled": False})["reason"] == "Scribe is disabled in Stronghold Admin."


def test_an_override_wins_over_the_parent_token():
    record = {"token": "parent"}
    assert token_for(record, {"origin_id": "o1"}) == "parent"
    assert token_for(record, {"origin_id": "o2", "header_value": "second"}) == "second"


def test_the_view_never_carries_a_token(tmp_path):
    record = {"enabled": True, "service_id": "s", "token": "parent-secret",
              "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "override-secret"}]}
    shown = view("bard", record, {"o1": "http://bard:29400"}.get)
    assert "secret" not in str(shown)
    assert shown["has_token"] is True and shown["label"] == "Bard" and shown["ready"] is True
    assert shown["origins"] == [{"origin_id": "o1", "origin": "http://bard:29400", "has_override": False},
                                {"origin_id": "o2", "origin": None, "has_override": True}]


def test_put_get_and_clear_round_trip(tmp_path):
    store = ToolStore(tmp_path / "settings.db")
    record = {"enabled": False, "service_id": "s", "origins": [{"origin_id": "o1"}], "token": "t"}
    store.put("reader", record)
    assert store.get("reader") == record
    store.clear("reader")
    assert store.get("reader")["origins"] == []
