from fastapi.testclient import TestClient

from src.api import create_app

TOKEN = "t0ken"
IDENTITY = {
    "X-Requester-Uid": "u-1",
    "X-Requester-Username": "ana",
    "X-Requester-Email": "ana@example.com",
}


def client(token: str = TOKEN) -> TestClient:
    return TestClient(create_app(token))


def test_health_is_open():
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_a_missing_token():
    response = client().get("/whoami", headers=IDENTITY)
    assert response.status_code == 401
    assert response.json() == {"error": "Invalid or missing internal API token"}


def test_rejects_a_wrong_token():
    response = client().get("/whoami", headers={**IDENTITY, "X-Internal-Token": "nope"})
    assert response.status_code == 401


def test_whoami_returns_the_requester():
    response = client().get("/whoami", headers={**IDENTITY, "X-Internal-Token": TOKEN})
    assert response.status_code == 200
    assert response.json() == {"uid": "u-1", "username": "ana", "email": "ana@example.com"}


def test_missing_uid_is_a_bad_request():
    headers = {"X-Internal-Token": TOKEN, "X-Requester-Username": "ana"}
    response = client().get("/whoami", headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Missing requester identity"}


def test_open_when_no_token_is_configured():
    response = client("").get("/whoami", headers=IDENTITY)
    assert response.status_code == 200
