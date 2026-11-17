"""/admin/tool-tokens: Stronghold's tokens for Bard, Scribe and Reader are saved in its settings database,
used by the next request, and never returned."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src import tool_tokens


def rows(response) -> dict[str, dict]:
    return {row["name"]: row for row in response.json()["services"]}


def test_a_saved_token_is_used_at_once_and_never_returned(client: TestClient) -> None:
    assert [row["name"] for row in client.get("/admin/tool-tokens").json()["services"]] == ["bard", "scribe", "reader"]

    saved = client.put("/admin/tool-tokens", json={"reader": "rd-secret"})

    assert saved.status_code == 200 and "rd-secret" not in saved.text and "rd-secret" not in client.get("/admin/tool-tokens").text
    assert rows(saved)["reader"] == {"name": "reader", "label": "Reader", "has_token": True, "stored": True}
    assert client.app.state.reader._token == "rd-secret"
    assert tool_tokens.stored(client.app.state.settings.data_dir / "settings.db") == {"reader": "rd-secret"}


def test_removing_a_saved_token_clears_it(client: TestClient) -> None:
    client.put("/admin/tool-tokens", json={"scribe": "sc-secret"})

    removed = client.put("/admin/tool-tokens", json={"scribe": None})

    assert rows(removed)["scribe"]["stored"] is False and client.app.state.scribe.has_token is False


def test_a_bad_change_saves_nothing(client: TestClient) -> None:
    for bad in ({}, {"made_up": "x"}, {"bard": "  "}, {"bard": "x" * 501}):
        assert client.put("/admin/tool-tokens", json=bad).status_code in (400, 422)
    answer = client.put("/admin/tool-tokens", json={"bard": "ok-token", "made_up": "x"})

    assert answer.status_code == 400 and answer.json()["detail"] == "Unknown tool service: made_up."
    assert tool_tokens.stored(client.app.state.settings.data_dir / "settings.db") == {}
