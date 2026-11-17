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


def test_the_connections_page_passes_through_to_treasury_and_is_logged(client, db_gateway):
    admin = as_admin(client)

    assert admin.get("/api/admin/treasury/connections").status_code == 200
    spec = {"type": "sqlite", "path": "reports.db"}
    assert admin.put("/api/admin/treasury/connections/reports", json=spec).status_code == 200
    assert admin.delete("/api/admin/treasury/connections/reports").status_code == 200
    assert admin.put("/api/admin/treasury/default-cache", json={"ttl_seconds": 10}).status_code == 200
    assert admin.put("/api/admin/treasury/default-cache").status_code == 200
    assert db_gateway.admin_calls == [
        ("GET", "/admin/connections", None), ("PUT", "/admin/connections/reports", spec),
        ("DELETE", "/admin/connections/reports", None), ("PUT", "/admin/default-cache", {"ttl_seconds": 10.0}),
        ("PUT", "/admin/default-cache", None),
    ]
    uid = admin.get("/api/auth/me").json()["id"]
    logged = " ".join(entry["message"] for entry in admin.get("/api/logs/action", params={"actor": uid}).json())
    assert "Saved Treasury connection 'reports'" in logged and "Removed Treasury connection 'reports'" in logged


def test_a_refusal_from_treasury_is_shown_and_an_outage_is_a_502(client, db_gateway):
    admin = as_admin(client)
    db_gateway.admin_refusal = 'The dsn must be a placeholder like "${POSTGRES_DSN}"'

    refused = admin.put("/api/admin/treasury/connections/pg", json={"type": "postgres", "dsn": "x"})
    assert (refused.status_code, refused.json()["detail"]) == (400, 'The dsn must be a placeholder like "${POSTGRES_DSN}"')

    from src.services.db_gateway import DbGatewayUnavailable

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("down")

    client.app.state.db_gateway.admin = down
    assert admin.get("/api/admin/treasury/connections").status_code == 502


def test_the_connections_routes_need_settings_manage(client, email, db_gateway):
    assert client.get("/api/admin/treasury/connections").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")

    assert client.get("/api/admin/treasury/connections").status_code == 403
    assert client.put("/api/admin/treasury/connections/x", json={"type": "sqlite", "path": "x.db"}).status_code == 403
    assert client.delete("/api/admin/treasury/connections/x").status_code == 403
    assert client.put("/api/admin/treasury/default-cache", json={"ttl_seconds": 1}).status_code == 403
    assert db_gateway.admin_calls == []


def test_services_routes_forward_pin_unpin_and_audit_without_addresses(client, db_gateway):
    admin = as_admin(client)
    assert admin.get("/api/admin/treasury/services").json() == {"services": []}
    body = {"url": "http://armory.lan:29600"}
    assert admin.put("/api/admin/treasury/services/armory", json=body).status_code == 200
    assert admin.delete("/api/admin/treasury/services/armory").status_code == 200
    assert db_gateway.admin_calls == [
        ("GET", "/admin/services", None), ("PUT", "/admin/services/armory", body),
        ("DELETE", "/admin/services/armory", None),
    ]
    uid = admin.get("/api/auth/me").json()["id"]
    entries = admin.get("/api/logs/action", params={"actor": uid}).json()
    logged = " ".join(entry["message"] for entry in entries)
    assert "Pinned Treasury service 'armory'" in logged
    assert "Unpinned Treasury service 'armory'" in logged
    assert body["url"] not in logged


def test_services_routes_need_settings_manage(client, email, db_gateway):
    assert client.get("/api/admin/treasury/services").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/admin/treasury/services").status_code == 403
    assert client.put("/api/admin/treasury/services/armory", json={"url": "http://x:1"}).status_code == 403
    assert client.delete("/api/admin/treasury/services/armory").status_code == 403
    assert db_gateway.admin_calls == []


def test_services_routes_report_refusals_and_outages(client, db_gateway):
    from src.services.db_gateway import DbGatewayUnavailable
    admin = as_admin(client)
    db_gateway.admin_refusal = "an address looks like http://host:port"
    response = admin.put("/api/admin/treasury/services/armory", json={"url": "bad"})
    assert (response.status_code, response.json()["detail"]) == (400, db_gateway.admin_refusal)

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("down")

    client.app.state.db_gateway.admin = down
    assert admin.get("/api/admin/treasury/services").status_code == 502
