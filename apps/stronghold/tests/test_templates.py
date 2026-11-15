from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.templates import store as template_service
from tests.helpers import as_admin, login, uids


def create(client: TestClient, name: str = "Review", body: str = "Please review this:") :
    return client.post("/templates", json={"name": name, "body": body})


def listing(client: TestClient) -> list[dict]:
    return client.get("/templates").json()


# --- access -------------------------------------------------------------------


def test_templates_are_private_per_account(client: TestClient) -> None:
    login(client, "alice")
    mine = create(client, "Mine", "secret plan").json()

    login(client, "bob")

    assert listing(client) == []
    assert client.put(f"/templates/{mine['id']}", json={"name": "x", "body": "y"}).status_code == 404
    assert client.delete(f"/templates/{mine['id']}").status_code == 404
    # Bob may use the same name: names are unique per account, not globally.
    assert create(client, "Mine", "bob's").status_code == 201
    login(client, "alice")
    assert [t["body"] for t in listing(client)] == ["secret plan"]


# --- CRUD ---------------------------------------------------------------------


def test_create_list_update_delete(client: TestClient) -> None:
    as_admin(client)

    created = create(client, "  Code   review ", "Line one\n  indented line\n")

    assert created.status_code == 201
    template = created.json()
    assert template["name"] == "Code review"  # trimmed, inner whitespace collapsed
    assert template["body"] == "Line one\n  indented line\n"  # the body is kept as typed
    assert listing(client) == [template]

    updated = client.put(f"/templates/{template['id']}", json={"name": "Review v2", "body": "New text"})
    assert updated.status_code == 200
    assert (updated.json()["name"], updated.json()["body"]) == ("Review v2", "New text")
    assert updated.json()["created_at"] == template["created_at"]

    assert client.delete(f"/templates/{template['id']}").status_code == 204
    assert listing(client) == []
    assert client.delete(f"/templates/{template['id']}").status_code == 404


def test_list_puts_the_most_recently_edited_first(client: TestClient) -> None:
    as_admin(client)
    first = create(client, "First", "1").json()
    create(client, "Second", "2")
    assert [t["name"] for t in listing(client)] == ["Second", "First"]

    client.put(f"/templates/{first['id']}", json={"name": "First", "body": "1 edited"})

    assert [t["name"] for t in listing(client)] == ["First", "Second"]


def test_unknown_or_out_of_range_ids(client: TestClient) -> None:
    as_admin(client)
    body = {"name": "x", "body": "y"}

    assert client.put(f"/templates/{'0' * 32}", json=body).status_code == 404
    assert client.delete(f"/templates/{'0' * 32}").status_code == 404
    assert client.put("/templates/0", json=body).status_code == 422
    assert client.delete("/templates/not-a-number").status_code == 422


# --- names --------------------------------------------------------------------


def test_names_are_unique_per_account_ignoring_case(client: TestClient) -> None:
    as_admin(client)
    create(client, "Review")

    duplicate = create(client, "  REVIEW  ")

    assert duplicate.status_code == 409
    assert "Review" in duplicate.json()["detail"] or "REVIEW" in duplicate.json()["detail"]
    assert len(listing(client)) == 1


def test_renaming_onto_another_name_is_refused_but_keeping_your_own_is_fine(client: TestClient) -> None:
    as_admin(client)
    a = create(client, "Alpha", "a").json()
    b = create(client, "Beta", "b").json()

    assert client.put(f"/templates/{b['id']}", json={"name": "alpha", "body": "b"}).status_code == 409
    # Changing only the case of its own name is an edit, not a clash.
    assert client.put(f"/templates/{a['id']}", json={"name": "ALPHA", "body": "a"}).status_code == 200
    assert {t["name"] for t in listing(client)} == {"ALPHA", "Beta"}


def test_a_failed_rename_leaves_the_template_as_it_was(client: TestClient) -> None:
    as_admin(client)
    create(client, "Alpha", "a")
    b = create(client, "Beta", "old body").json()

    client.put(f"/templates/{b['id']}", json={"name": "alpha", "body": "new body"})

    assert {t["name"]: t["body"] for t in listing(client)} == {"Alpha": "a", "Beta": "old body"}


def test_non_ascii_names_fold_too(client: TestClient) -> None:
    as_admin(client)
    create(client, "Straße")

    assert create(client, "STRASSE").status_code == 409


# --- validation and limits -----------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "body": "x"},
        {"name": "   ", "body": "x"},
        {"name": "x", "body": ""},
        {"name": "x", "body": " \n\t "},
        {"name": "n" * 61, "body": "x"},
        {"name": "x", "body": "b" * (template_service.BODY_MAX + 1)},
        {"name": "x"},
        {"body": "x"},
        {"name": 5, "body": "x"},
    ],
)
def test_validation(client: TestClient, payload: dict) -> None:
    as_admin(client)

    assert client.post("/templates", json=payload).status_code == 422
    assert listing(client) == []


def test_the_longest_allowed_name_and_body_are_accepted(client: TestClient) -> None:
    as_admin(client)

    response = create(client, "n" * template_service.NAME_MAX, "b" * template_service.BODY_MAX)

    assert response.status_code == 201


def test_template_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template_service, "MAX_TEMPLATES_PER_ACCOUNT", 2)
    as_admin(client)
    create(client, "One")
    create(client, "Two")

    response = create(client, "Three")

    assert response.status_code == 409
    assert "At most 2" in response.json()["detail"]
    assert len(listing(client)) == 2
    # Editing and deleting still work at the limit, and deleting frees a slot.
    assert client.delete(f"/templates/{listing(client)[0]['id']}").status_code == 204
    assert create(client, "Three").status_code == 201


# --- account deletion -----------------------------------------------------------


def test_templates_go_with_their_account(client: TestClient, db_gateway) -> None:
    login(client, "alice")
    create(client)
    login(client, "bob")
    create(client, "Bob's")

    assert client.delete(f"/templates/accounts/{uids(client)['alice']}").status_code == 204

    assert [doc["name"] for doc in db_gateway.records.values()] == ["Bob's"]


def test_gateway_down_gives_503(client: TestClient, db_gateway, monkeypatch) -> None:
    from src.document_store import DbGatewayUnavailable

    as_admin(client)

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("db_gateway is not reachable")

    for method in ("get", "put", "create", "delete", "query"):
        monkeypatch.setattr(db_gateway, method, down)

    assert client.get("/templates").status_code == 503
    assert create(client).status_code == 503
    assert client.delete(f"/templates/accounts/{uids(client)['root']}").status_code == 503
