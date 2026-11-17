"""/admin/usage-settings: the limits and the price table are saved in Stronghold's settings database and used at once."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import load_settings
from src.usage import admin_settings


def db(client: TestClient):
    return client.app.state.settings.data_dir / "settings.db"


def test_defaults_then_a_limit_change_is_used_at_once_and_kept(client: TestClient) -> None:
    first = client.get("/admin/usage-settings").json()
    assert first["usage"]["six_hour_token_limit"] == 1_000_000 and first["pricing"]["models"] == {}
    assert first["stored"] == {"usage": False, "pricing": False}

    saved = client.put("/admin/usage-settings", json={"usage": {"six_hour_token_limit": 250_000}})

    assert saved.status_code == 200 and saved.json()["usage"]["six_hour_token_limit"] == 250_000
    assert saved.json()["usage"]["weekly_token_limit"] == 5_000_000 and saved.json()["stored"]["usage"] is True
    assert client.app.state.settings.usage.six_hour_token_limit == 250_000  # the services share this object
    usage, _ = admin_settings.load(db(client))
    assert usage.six_hour_token_limit == 250_000


def test_the_price_table_is_replaced_and_prices_use_it_at_once(client: TestClient) -> None:
    table = {"models": {"Sonnet": {"input": 3, "output": 15}}}

    saved = client.put("/admin/usage-settings", json={"pricing": table})

    assert saved.status_code == 200 and saved.json()["pricing"]["models"]["Sonnet"] == {"input": 3.0, "output": 15.0}
    assert client.app.state.pricing.cost("sonnet", 1_000_000, 1_000_000) == 18.0
    again = client.put("/admin/usage-settings", json={"pricing": {"models": {}}})
    assert again.json()["pricing"]["models"] == {} and client.app.state.pricing.cost("sonnet", 1, 1) is None
    assert client.get("/usage/pricing").json()["models"] == {}


def test_a_bad_change_is_refused_and_saves_nothing(client: TestClient) -> None:
    for bad in (
        {}, {"other": 1}, {"usage": {}}, {"usage": {"made_up": 1}}, {"usage": {"six_hour_token_limit": -1}},
        {"usage": {"auto_summarize_ratio": 2}}, {"pricing": {"currency": "EUR"}},
        {"pricing": {"models": {"X": {"input": -1, "output": 0}}}}, {"pricing": {"models": {"X": {"input": 1}}}},
        {"pricing": {"models": []}}, {"pricing": {"extra": 1}},
    ):
        refused = client.put("/admin/usage-settings", json=bad)
        assert refused.status_code == 400 and refused.json()["detail"], bad
    mixed = client.put("/admin/usage-settings", json={"usage": {"weekly_token_limit": 9}, "pricing": {"currency": "EUR"}})
    assert mixed.status_code == 400
    assert client.app.state.settings.usage.weekly_token_limit == 5_000_000
    assert client.get("/admin/usage-settings").json()["stored"] == {"usage": False, "pricing": False}


def test_load_settings_applies_what_was_saved(client: TestClient, monkeypatch) -> None:
    client.put("/admin/usage-settings", json={"usage": {"weekly_token_limit": 7}, "pricing": {"models": {"M": {"input": 1, "output": 2}}}})
    monkeypatch.setenv("STRONGHOLD_DATA_DIR", str(client.app.state.settings.data_dir))

    loaded = load_settings()

    assert loaded.usage.weekly_token_limit == 7 and loaded.pricing.models["M"].output == 2.0
