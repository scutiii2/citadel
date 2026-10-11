from dataclasses import fields
from src.config import Settings

def test_old_game_proxy_is_not_routed(client):
    assert client.get("/api/ascension/profile").status_code == 404

def test_game_registry_replaces_the_old_backend_url_setting():
    assert ("ascension" + "_url") not in {field.name for field in fields(Settings)}
