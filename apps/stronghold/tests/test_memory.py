"""Account deletion purges legacy assistant memory from Armory."""

import httpx


def test_purge_deletes_the_owner_once_and_reports_a_refusal(client, armory):
    armory.handler = lambda request: httpx.Response(204)
    assert client.delete("/memory/accounts/carol-uid").status_code == 204
    assert [(r.method, r.url.path) for r in armory.requests] == [("DELETE", "/memory/owners/carol-uid")]
    armory.handler = lambda request: httpx.Response(500)
    assert client.delete("/memory/accounts/carol-uid").status_code == 502
