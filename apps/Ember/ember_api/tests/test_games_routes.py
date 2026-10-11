import asyncio
from urllib.parse import urlsplit, parse_qs
import pytest
from sqlalchemy import update
from src.models import Game
from src.services.game_manifest import ManifestError
from tests.test_games_registry import FakeFetcher
from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin


def register(client, url="http://localhost:8060"):
    response = client.post("/api/games", json={"url": url})
    assert response.status_code == 201, response.text
    return response.json()


def launch(client):
    response = client.post("/api/games/ascension/launch", json={})
    assert response.status_code == 200, response.text
    url = response.json()["url"]
    assert url.startswith("http://localhost:8060/#ticket=")
    return parse_qs(urlsplit(url).fragment)["ticket"][0]


def redeem(client, ticket, game_id="ascension", token="test-internal"):
    return client.post("/internal/games/tickets/redeem", json={"ticket": ticket, "game_id": game_id}, headers={"X-Internal-Token": token})


def test_registry_launch_redeem_and_audit(client_factory):
    fetcher = FakeFetcher()
    client = client_factory(game_fetcher=fetcher, internal_token="test-internal")
    assert client.get("/api/games").status_code == 401
    as_admin(client)
    me = client.get("/api/auth/me").json()
    game = register(client)
    assert game["id"] == "ascension" and game["enabled"] is True
    assert client.post("/api/games", json={"url": "http://localhost:8060"}).status_code == 409
    assert client.get("/api/games").json()["games"][0]["name"] == "Ascension"
    assert client.get("/api/games/registry").json()["games"][0]["url"] == game["url"]
    ticket = launch(client)
    # Internal authentication never falls back to the browser cookie.
    assert redeem(client, ticket, token="wrong").json() == {"detail": "Invalid ticket"}
    assert redeem(client, ticket, game_id="other").status_code == 401
    client.cookies.clear()
    response = redeem(client, ticket)
    assert response.status_code == 200
    assert response.json() == {"account_id": str(me["id"]), "display_name": me["username"]}
    assert redeem(client, ticket).json() == {"detail": "Invalid ticket"}
    as_admin(client)
    fetcher.raw.update(name="Updated", version="2")
    assert client.post("/api/games/ascension/refresh", json={}).json()["name"] == "Updated"
    outstanding = launch(client)
    assert client.delete("/api/games/ascension").status_code == 204
    assert client.post("/api/games/ascension/launch", json={}).status_code == 404
    assert redeem(client, outstanding).status_code == 401
    assert client.get("/api/games").json() == {"games": []}
    permissions = client.get("/api/admin/permissions").json()
    assert {"name": "games.ascension.play", "description": "Play ascension"} in permissions
    entries = client.get("/api/logs/action", params={"actor": me["id"]}).json()
    games = [entry for entry in entries if entry["source"].startswith("games.")]
    assert sorted(entry["source"] for entry in games) == ["games.deregister", "games.launch", "games.launch", "games.refresh", "games.register"]
    assert ticket not in str(entries) and outstanding not in str(entries)


def test_members_only_see_and_launch_permitted_games(client_factory, email):
    fetcher = FakeFetcher()
    client = client_factory(game_fetcher=fetcher)
    as_admin(client)
    make_member(client, email)
    as_admin(client)
    register(client)
    fetcher.raw.update(id="other", name="Other")
    register(client, "http://localhost:8061")
    member = role_by_name(client, "Member")
    assert client.put(f"/api/admin/roles/{member['id']}/permissions/games.ascension.play").status_code == 200
    login(client, "alice")
    assert [g["id"] for g in client.get("/api/games").json()["games"]] == ["ascension"]
    launch(client)
    assert client.post("/api/games/other/launch", json={}).status_code == 403
    assert client.post("/api/games/missing/launch", json={}).status_code == 404
    assert client.get("/api/games/registry").status_code == 403
    for method, path, body in (("POST", "/api/games", {"url": "http://localhost:8062"}), ("POST", "/api/games/ascension/refresh", {}), ("DELETE", "/api/games/ascension", None)):
        assert client.request(method, path, json=body).status_code == 403


def test_disabled_games_are_admin_visible_but_cannot_launch(client_factory):
    client = client_factory(game_fetcher=FakeFetcher())
    as_admin(client)
    register(client)
    async def disable():
        async with client.app.state.database.sessions() as session:
            await session.execute(update(Game).values(enabled=False))
            await session.commit()
    client.portal.call(disable)
    assert client.get("/api/games").json() == {"games": []}
    assert client.get("/api/games/registry").json()["games"][0]["enabled"] is False
    assert client.post("/api/games/ascension/launch", json={}).status_code == 404


def test_manifest_errors_and_private_url_setting(client_factory):
    class BadFetcher:
        async def fetch(self, url):
            raise ManifestError("Invalid manifest id")
    client = client_factory(game_fetcher=BadFetcher(), games_allow_private_urls=False)
    as_admin(client)
    assert client.post("/api/games", json={"url": "https://game.example"}).status_code == 400
    assert client.post("/api/games", json={"url": "http://127.0.0.1"}).status_code == 400
    assert client.post("/api/games", json={"url": "https://game.example", "extra": True}).status_code == 422
    assert client.post("/api/games/missing/refresh", json={}).status_code == 404
    assert client.delete("/api/games/missing").status_code == 404


def test_internal_auth_and_malformed_tickets(client_factory):
    client = client_factory()
    assert redeem(client, "anything").status_code == 503
    client.app.state.internal_token = "test-internal"
    for body in ({}, {"ticket": 42, "game_id": "ascension"}, {"ticket": "x", "game_id": "ascension", "extra": 1}):
        response = client.post("/internal/games/tickets/redeem", json=body, headers={"X-Internal-Token": "test-internal"})
        assert response.status_code == 401 and response.json() == {"detail": "Invalid ticket"}
    assert client.post("/internal/games/tickets/redeem", json={"ticket": "x", "game_id": "ascension"}).status_code == 401


def test_private_url_config_loads_without_secrets(monkeypatch, tmp_path):
    from src import config
    monkeypatch.setattr(config, "CONFIGS_DIR", tmp_path)
    monkeypatch.setattr(config, "ensure_env_file", lambda *args: None)
    (tmp_path / "config_app.json").write_text('{"games_allow_private_urls": false}')
    assert config.load_settings().games_allow_private_urls is False
    (tmp_path / "config_app.json").write_text('{}')
    assert config.load_settings().games_allow_private_urls is True
