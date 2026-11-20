import json

import httpx

from tests.auth_helpers import assertion
from tests.test_admin import login, make_member
from tests.test_registration import as_admin
from tests.test_turn_passthrough import action_log

JSON = {"Content-Type": "application/json"}


def test_an_administrator_reads_and_changes_the_settings(client, upstream):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(200, json={"long_term": {"max_files": 50}})
    upstream.requests.clear()
    assert client.get("/api/admin/stronghold-brain-settings").json() == {"long_term": {"max_files": 50}}
    changed = client.put("/api/admin/stronghold-brain-settings", json={"long_term": {"max_files": 50}}, headers=JSON)
    assert changed.status_code == 200
    get, put = upstream.requests
    assert (get.method, get.url.path, put.method, put.url.path) == ("GET", "/admin/brain-settings", "PUT", "/admin/brain-settings")
    assert json.loads(put.content) == {"long_term": {"max_files": 50}}
    assert assertion(put, "stronghold")["iss"] == "portcullis"
    assert "settings.brain" in action_log(client)


def test_a_member_without_settings_manage_is_refused(client, email, upstream):
    make_member(client, email, verify=False)
    login(client, "alice")
    upstream.requests.clear()
    assert client.get("/api/admin/stronghold-brain-settings").status_code in (401, 403)
    assert client.put("/api/admin/stronghold-brain-settings", json={"stack": {"max_items": 9}}, headers=JSON).status_code in (401, 403)
    assert not upstream.requests


def test_a_refused_change_is_passed_back(client, upstream):
    as_admin(client)
    upstream.handler = lambda _: httpx.Response(400, json={"detail": "max_files must be a whole number from 1 to 5000."})
    answer = client.put("/api/admin/stronghold-brain-settings", json={"long_term": {"max_files": 0}}, headers=JSON)
    assert answer.status_code == 400 and "max_files" in answer.json()["detail"]
