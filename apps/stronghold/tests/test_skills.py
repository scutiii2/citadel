"""/skills: the user's review of what agents proposed. The store is Stronghold's own brain folder."""

import pytest

from tests.auth_helpers import identity

EDIT = {"title": "Reboot an app", "when_to_use": "an app freezes", "steps": "kill it, then launch it", "tools": "tool_srv_restartApp"}
KEYS = {"id", "title", "when_to_use", "steps", "tools", "status", "successes", "failures", "created_at", "failing"}


def propose(client, uid="u-1", title="Restart an app"):
    skills = client.app.state.skill_files
    skill, _ = client.portal.call(skills.propose, uid, title, "an app is hung", "stop it, then start it", "tool_srv_stopApp")
    return skill.id


def test_skills_need_the_requester_identity(client):
    assert client.get("/skills", headers=identity(uid="")).status_code == 400


def test_the_list_shows_proposals_with_the_failing_flag(client):
    assert client.get("/skills").json() == []
    skill_id = propose(client)
    shown = client.get("/skills").json()
    assert len(shown) == 1 and set(shown[0]) == KEYS
    assert (shown[0]["id"], shown[0]["status"], shown[0]["failing"]) == (skill_id, "proposed", False)


def test_the_user_approves_retires_and_reproposes(client):
    skill_id = propose(client)
    for status in ("active", "retired", "proposed"):
        answer = client.put(f"/skills/{skill_id}/status", json={"status": status})
        assert answer.status_code == 200 and answer.json()["status"] == status


@pytest.mark.parametrize("body", [{"status": "banana"}, {}, {"status": 5}])
def test_status_is_validated(client, body):
    skill_id = propose(client)
    assert client.put(f"/skills/{skill_id}/status", json=body).status_code == 422
    assert client.get("/skills").json()[0]["status"] == "proposed"


def test_an_unknown_skill_is_404(client):
    assert client.put("/skills/9/status", json={"status": "active"}).status_code == 404
    assert client.put("/skills/9", json=EDIT).status_code == 404
    assert client.delete("/skills/9").status_code == 404
    assert client.put("/skills/0/status", json={"status": "active"}).status_code == 422


def test_editing_rewrites_the_text_and_resets_the_counts(client):
    skill_id = propose(client)
    client.put(f"/skills/{skill_id}/status", json={"status": "active"})
    client.portal.call(client.app.state.skill_files.mark, "u-1", skill_id, "failure")
    edited = client.put(f"/skills/{skill_id}", json={**EDIT, "title": "  Reboot   an app "})
    assert edited.status_code == 200
    body = edited.json()
    assert (body["title"], body["status"], body["failures"]) == ("Reboot an app", "active", 0)


def test_edit_refusals(client):
    first, second = propose(client), propose(client, title="Other")
    assert client.put(f"/skills/{second}", json={**EDIT, "title": "restart an app"}).status_code == 409
    assert client.put(f"/skills/{first}", json={**EDIT, "title": ""}).status_code == 422
    assert client.put(f"/skills/{first}", json={**EDIT, "steps": "x" * 1201}).status_code == 422
    assert client.put(f"/skills/{first}", json={"title": "only a title"}).status_code == 422


def test_delete_removes_one_skill(client):
    skill_id = propose(client)
    assert client.delete(f"/skills/{skill_id}").status_code == 204
    assert client.get("/skills").json() == []


def test_another_account_cannot_see_or_touch_a_skill(client):
    skill_id = propose(client)
    other = identity(uid="u-2", username="bo", email="bo@example.com")
    assert client.get("/skills", headers=other).json() == []
    assert client.put(f"/skills/{skill_id}/status", json={"status": "active"}, headers=other).status_code == 404
    assert client.put(f"/skills/{skill_id}", json=EDIT, headers=other).status_code == 404
    assert client.delete(f"/skills/{skill_id}", headers=other).status_code == 404
    assert client.get("/skills").json()[0]["status"] == "proposed"


def test_purge_deletes_only_that_accounts_skills(client):
    propose(client)
    propose(client, uid="u-2")
    assert client.delete("/skills/accounts/u-1").status_code == 204
    assert client.get("/skills").json() == []
    assert len(client.portal.call(client.app.state.skill_files.list, "u-2")) == 1
    assert client.delete("/skills/accounts/u-1").status_code == 204  # nothing left: still fine
    assert client.delete("/skills/accounts/bad.uid").status_code == 422


def test_the_active_cap_is_a_409_with_a_readable_reason(client, monkeypatch):
    from src.brain import skills as skill_module

    monkeypatch.setattr(skill_module, "MAX_ACTIVE", 1)
    first, second = propose(client), propose(client, title="Other")
    assert client.put(f"/skills/{first}/status", json={"status": "active"}).status_code == 200
    answer = client.put(f"/skills/{second}/status", json={"status": "active"})
    assert answer.status_code == 409 and "Retire one first" in answer.json()["detail"]


def test_only_portcullis_can_review_or_purge_skills(client, as_service):
    skill_id = propose(client)
    armory = as_service("armory")
    approval = armory.put(f"/skills/{skill_id}/status", json={"status": "active"}, headers=identity())
    assert approval.status_code == 403
    assert armory.delete("/skills/accounts/u-1").status_code == 403
    assert client.get("/skills").json()[0]["status"] == "proposed"


def test_edit_validation_and_audit_do_not_echo_skill_text(client, platform, caplog):
    skill_id = propose(client)
    too_long = "private-edit-marker" * 100
    refused = client.put(f"/skills/{skill_id}", json={**EDIT, "steps": too_long})
    assert refused.status_code == 422 and "private-edit-marker" not in refused.text
    assert client.put(f"/skills/{skill_id}/status", json={"status": "active"}).status_code == 200
    assert client.put(f"/skills/{skill_id}", json=EDIT).status_code == 200
    assert client.delete(f"/skills/{skill_id}").status_code == 204
    assert platform.actions == [
        ("u-1", "skills.status", "Set a skill to active"),
        ("u-1", "skills.edit", "Edited a skill"),
        ("u-1", "skills.delete", "Deleted a skill"),
    ]
    assert "private-edit-marker" not in caplog.text


def test_health_survives_a_brain_root_that_cannot_hold_skills(make_client, monkeypatch, tmp_path):
    unavailable = tmp_path / "occupied"
    unavailable.touch()
    monkeypatch.setenv("STRONGHOLD_BRAIN_ROOT", str(unavailable))
    app = make_client()
    assert app.get("/health").status_code == 200
    assert app.get("/skills").status_code == 503
    assert app.delete("/skills/accounts/u-1").status_code == 503


def test_a_file_at_the_skills_directory_is_a_readable_refusal(client):
    folder = client.app.state.brain_files.root / "accounts" / "u-1" / ".skills"
    folder.parent.mkdir(parents=True)
    folder.touch()
    assert client.get("/health").status_code == 200
    answer = client.get("/skills")
    assert answer.status_code == 503
    assert answer.json()["detail"] == "Skill storage is unavailable."
