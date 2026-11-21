import pytest

from src.brain.records import normalize_tags


@pytest.mark.parametrize("method, path", [
    ("GET", "/notes"), ("POST", "/notes"), ("GET", "/notes/tags"), ("POST", "/notes/suggest-tags"),
    ("POST", "/notes/generate-tag"), ("GET", "/notes/" + "a" * 32), ("PUT", "/notes/" + "a" * 32),
    ("DELETE", "/notes/" + "a" * 32), ("GET", "/memory"), ("POST", "/memory"), ("PUT", "/memory/1"), ("DELETE", "/memory/1"),
])
def test_the_old_routes_are_gone(client, method, path):
    assert client.request(method, path, json={}).status_code == 404


def test_the_purge_routes_stay(client):
    assert client.delete("/notes/accounts/u-9").status_code == 204


def test_normalize_tags_lives_with_the_brain_records():
    assert normalize_tags.__module__ == "src.brain.records"
    assert normalize_tags([" Tea ", "tea", "Green_Tea"]) == ["tea", "green_tea"]
    with pytest.raises(ValueError):
        normalize_tags(["bad tag!"])
