from tests.auth_helpers import IdentityHeaders

BO = IdentityHeaders(uid="u-2", username="bob", email="bob@example.com")
CY = IdentityHeaders(uid="u-3", username="cyd", email="cyd@example.com")
WRITER = {"chat.use", "brain.global.write"}


def make_file(client, title="Diet", body="Likes [diet](private/diet.md)."):
    return client.post("/brain/files", json={"title": title, "body": body}).json()


def share(client, file_id, recipient="bob", **extra):
    return client.post("/brain/shares", json={"kind": "file", "file_id": file_id, "recipient": recipient, **extra})


def test_share_inbox_preview_accept_and_logs(client, platform):
    file = make_file(client)
    sent = share(client, file["id"])
    assert sent.status_code == 201, sent.text
    given = sent.json()
    me = client.get("/whoami").json()["username"]
    assert (given["status"], given["recipient"], given["sender"]) == ("pending", "bob", me)
    assert [s["id"] for s in client.get("/brain/shares/sent").json()["shares"]] == [given["id"]]
    assert client.get("/brain/shares/inbox").json()["shares"] == []
    inbox = client.get("/brain/shares/inbox", headers=BO).json()["shares"]
    assert [s["id"] for s in inbox] == [given["id"]] and "body" not in inbox[0]
    seen = client.get(f"/brain/shares/{given['id']}", headers=BO).json()
    assert seen["body"] == "Likes diet." and "untrusted" in seen["notice"].lower()
    assert client.get(f"/brain/shares/{given['id']}", headers=CY).status_code == 404
    done = client.post(f"/brain/shares/{given['id']}/accept", json={"folder": "friends"}, headers=BO)
    assert done.status_code == 200 and done.json()["status"] == "accepted"
    mine = client.get("/brain/files", headers=BO).json()["files"]
    assert [(f["source"], f["shared_from"], f["folder"]) for f in mine] == [("shared", me, "friends")]
    actions = [a for _, a, _ in platform.actions]
    assert "brain.share" in actions and "brain.share_accept" in actions
    assert all("Diet" not in m and "diet" not in m for _, _, m in platform.actions)


def test_unknown_inactive_self_and_blocking_recipients_all_look_alike(client, platform):
    file = make_file(client)
    assert share(client, file["id"], recipient="nobody").status_code == 404
    unknown = share(client, file["id"], recipient="nobody").json()["detail"]
    platform.granted["u-3"] = None
    inactive = share(client, file["id"], recipient="cyd")
    assert (inactive.status_code, inactive.json()["detail"]) == (404, unknown)
    me = client.get("/whoami").json()["username"]
    client.app.state.platform.usernames[me] = "u-1"
    assert client.put("/brain/blocks", json={"username": me}, headers=BO).status_code == 200
    blocked = share(client, file["id"])
    assert (blocked.status_code, blocked.json()["detail"]) == (404, unknown)
    self_share = share(client, file["id"], recipient=me)
    assert (self_share.status_code, self_share.json()["detail"]) == (404, unknown)
    assert [b["username"] for b in client.get("/brain/blocks", headers=BO).json()["blocks"]] == [me]
    assert client.delete("/brain/blocks/u-1", headers=BO).status_code == 204
    assert client.delete("/brain/blocks/u-1", headers=BO).status_code == 404
    assert share(client, file["id"]).status_code == 201


def test_revoke_decline_and_validation(client):
    file = make_file(client)
    given = share(client, file["id"]).json()
    assert client.delete(f"/brain/shares/{given['id']}", headers=BO).status_code == 404
    assert client.delete(f"/brain/shares/{given['id']}").status_code == 200
    second = share(client, file["id"]).json()
    assert client.post(f"/brain/shares/{second['id']}/decline", headers=BO).json()["status"] == "declined"
    for body in ({"kind": "file", "recipient": "bob"}, {"kind": "file", "file_id": file["id"]},
                 {"kind": "file", "file_id": file["id"], "recipient": "bob", "to_global": True},
                 {"kind": "banana", "file_id": file["id"], "recipient": "bob"}, {"kind": "section", "file_id": file["id"], "recipient": "bob"},
                 {"kind": "skill", "recipient": "bob"}, {"kind": "stack_item", "chat_id": "c1", "recipient": "bob"}):
        answer = client.post("/brain/shares", json=body)
        assert answer.status_code == 422 and "Diet" not in answer.text
    assert client.get("/brain/shares/not-hex").status_code == 422


def test_a_global_share_goes_to_the_review_queue(client, platform):
    file = make_file(client)
    given = client.post("/brain/shares", json={"kind": "file", "file_id": file["id"], "to_global": True}).json()
    assert given["recipient"] == "global brain"
    assert client.get("/brain/global/shares").status_code == 403
    platform.granted["u-2"] = WRITER
    queue = client.get("/brain/global/shares", headers=BO).json()["shares"]
    assert [s["id"] for s in queue] == [given["id"]]
    assert client.get(f"/brain/global/shares/{given['id']}", headers=BO).json()["body"] == "Likes diet."
    assert client.post(f"/brain/global/shares/{given['id']}/approve", headers=CY).status_code == 403
    done = client.post(f"/brain/global/shares/{given['id']}/approve", json={"title": "House diet", "folder": "policy"}, headers=BO)
    assert done.status_code == 200 and done.json()["status"] == "accepted"
    platform.granted["u-3"] = {"chat.use"}
    shown = client.get("/brain/global/files", headers=CY).json()["files"]
    me = client.get("/whoami").json()["username"]
    assert [(f["title"], f["shared_from"], f["folder"]) for f in shown] == [("House diet", me, "policy")]
    second = client.post("/brain/shares", json={"kind": "file", "file_id": file["id"], "to_global": True}).json()
    assert client.post(f"/brain/global/shares/{second['id']}/reject", headers=BO).json()["status"] == "rejected"
    assert client.get("/brain/global/shares", headers=BO).json()["shares"] == []
    assert "brain.global_review" in [a for _, a, _ in platform.actions]


def test_purge_removes_an_accounts_shares_and_blocks(client):
    file = make_file(client)
    share(client, file["id"])
    client.put("/brain/blocks", json={"username": "cyd"})
    assert client.delete("/brain/shares/accounts/u-1").status_code == 204
    assert client.get("/brain/shares/sent").json()["shares"] == [] and client.get("/brain/blocks").json()["blocks"] == []
    assert client.get("/brain/shares/inbox", headers=BO).json()["shares"] == []
    assert client.delete("/brain/shares/accounts/bad.uid").status_code == 422


def test_storage_errors_do_not_include_share_content(client, db_gateway, monkeypatch):
    from src.document_store import DbGatewayError

    file = make_file(client)
    async def refused(*_args):
        raise DbGatewayError("private storage response")

    monkeypatch.setattr(db_gateway, "put", refused)
    answer = share(client, file["id"])
    assert (answer.status_code, answer.json()) == (503, {"detail": "Storage is unavailable"})


def test_recipient_lookup_is_redacted_in_service_logs():
    import logging

    from src.log_privacy import UidLogFilter

    path = "/internal/accounts/by-username/sample-recipient"
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1, "%s", (path,), None)
    assert UidLogFilter().filter(record)
    assert "sample-recipient" not in record.getMessage()
