"""/api/admin/treasury: read-only view of Treasury's instances for the Treasury admin app."""

from tests.test_admin import login, make_member
from tests.test_registration import as_admin


def test_needs_a_login_and_settings_manage(client, email):
    assert client.get("/api/admin/treasury").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/admin/treasury").status_code == 403


def test_lists_instances_and_the_one_portcullis_uses(client):
    as_admin(client)
    body = client.get("/api/admin/treasury").json()
    assert body["reachable"] is True
    assert {"name": "stronghold", "connections": ["stronghold"]} in body["instances"]
    assert set(body["portcullis"]) == {"instance", "connection"}


def test_says_so_when_treasury_does_not_answer(client):
    from src.services.db_gateway import DbGatewayUnavailable

    async def down():
        raise DbGatewayUnavailable("down")

    as_admin(client)
    client.app.state.db_gateway.instances = down
    body = client.get("/api/admin/treasury").json()
    assert body == {"reachable": False, "instances": [], "portcullis": body["portcullis"]}
