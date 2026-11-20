import pytest

from src.brain.limits import load_limits, load_long_term


def db(client):
    return client.app.state.settings.data_dir / "settings.db"


def test_defaults_ranges_and_root(client):
    shown = client.get("/admin/brain-settings").json()
    assert shown["long_term"]["max_record_chars"] == 20_000 and shown["stack"]["max_items"] == 40
    assert shown["ranges"]["long_term"]["max_files"] == [1, 5000] and shown["ranges"]["stack"]["warn_ratio"] == [0.3, 0.95]
    assert shown["stored"] == {"stack": False, "long_term": False, "sharing": False}
    assert shown["root"].replace("\\", "/").endswith("/data/brain")


def test_a_long_term_change_is_used_at_once_and_kept(client):
    saved = client.put("/admin/brain-settings", json={"long_term": {"max_files": 50, "search_limit": 3}})
    assert saved.status_code == 200 and saved.json()["long_term"]["max_files"] == 50
    assert saved.json()["long_term"]["max_record_chars"] == 20_000 and saved.json()["stored"]["long_term"] is True
    assert client.app.state.brain_files.limits.max_files == 50
    assert load_long_term(db(client)).search_limit == 3
    client.put("/admin/brain-settings", json={"long_term": {"max_record_chars": 5000}})
    assert load_long_term(db(client)).max_files == 50 and load_long_term(db(client)).max_record_chars == 5000


def test_a_stack_change_is_used_at_once_and_kept(client):
    saved = client.put("/admin/brain-settings", json={"stack": {"max_items": 10, "warn_ratio": 0.5}})
    assert saved.status_code == 200
    assert client.app.state.stacks.limits.max_items == 10 and client.app.state.stacks.limits.warn_ratio == 0.5
    assert load_limits(db(client)).max_items == 10


@pytest.mark.parametrize("changes", [
    {}, {"nothing": {}}, {"stack": {}}, {"stack": "x"}, {"root": "/elsewhere"},
    {"long_term": {"root": "/elsewhere"}}, {"long_term": {"max_files": 0}}, {"long_term": {"max_files": 5001}},
    {"long_term": {"max_files": True}}, {"long_term": {"max_files": "10"}}, {"long_term": {"max_files": 1.5}},
    {"stack": {"warn_ratio": 0.99}}, {"stack": {"warn_ratio": "high"}}, {"stack": {"warn_ratio": True}},
    {"stack": {"max_items": 1}},
])
def test_bad_changes_are_refused_and_nothing_is_saved(client, changes):
    before = (client.app.state.stacks.limits, client.app.state.brain_files.limits)
    answer = client.put("/admin/brain-settings", json=changes)
    assert answer.status_code == 400 and answer.json()["detail"]
    assert (client.app.state.stacks.limits, client.app.state.brain_files.limits) == before
    assert client.get("/admin/brain-settings").json()["stored"] == {"stack": False, "long_term": False, "sharing": False}


def test_one_bad_part_saves_nothing(client):
    answer = client.put("/admin/brain-settings", json={"stack": {"max_items": 10}, "long_term": {"max_files": 0}})
    assert answer.status_code == 400
    assert client.app.state.stacks.limits.max_items == 40
    assert client.get("/admin/brain-settings").json()["stored"]["stack"] is False

def test_the_reported_root_changes_only_after_restart(client, tmp_path):
    from src.citadel_auth import settings_store

    before = client.get("/admin/brain-settings").json()["root"]
    settings_store.put(db(client), "brain", "root", str(tmp_path / "new-root"))
    assert client.get("/admin/brain-settings").json()["root"] == before
