import pytest

from src.brain.files import BrainError, BrainFiles
from src.brain.fragments import drop_private_links, extract_section
from src.brain.limits import LongTermLimits
from src.brain.records import Record, parse, render
from src.brain.skills import SkillFiles

U1 = "u-1"


def test_private_links_become_their_label_and_public_links_stay():
    text = "See [notes](private/notes.md) and [site](https://example.com) or [mail](mailto:a@b.c)."
    assert drop_private_links(text) == "See notes and [site](https://example.com) or [mail](mailto:a@b.c)."
    assert drop_private_links("![pic](a.png) and ![web](https://x.test/a.png)") == "pic and web"
    assert drop_private_links("[[Diet plan|my diet]] and [[Diet plan]] and [[Diet plan#Week 1]]") == "my diet and Diet plan and Diet plan"
    assert drop_private_links("plain text, no links") == "plain text, no links"


BODY = "intro\n\n# Setup\nstep one\n## Detail\nmore\n```\n# not a heading\n```\n# Usage\nrun it\n"


def test_a_section_runs_to_the_next_heading_of_the_same_or_higher_level():
    assert extract_section(BODY, "Setup") == "# Setup\nstep one\n## Detail\nmore\n```\n# not a heading\n```"
    assert extract_section(BODY, "  detail ") == "## Detail\nmore\n```\n# not a heading\n```"
    assert extract_section(BODY, "Usage") == "# Usage\nrun it"
    assert extract_section(BODY, "Missing") is None
    assert extract_section(BODY, "not a heading") is None


def test_shared_from_survives_a_round_trip_and_old_files_still_parse():
    record = Record("a" * 32, "T", "b", source="shared", shared_from="bo", created_at="x", updated_at="x")
    again = parse(render(record), folder="", fallback_id="f", fallback_title="t", fallback_time="x")
    assert (again.source, again.shared_from) == ("shared", "bo")
    plain = render(Record("a" * 32, "T", "b", created_at="x", updated_at="x"))
    assert "shared_from" not in plain
    assert parse(plain, folder="", fallback_id="f", fallback_title="t", fallback_time="x").shared_from == ""


@pytest.fixture
def brain(tmp_path):
    return BrainFiles(tmp_path / "brain", LongTermLimits(), refresh_seconds=0.0)


async def test_a_shared_file_is_user_editable_revertable_and_agent_read_only(brain):
    made = await brain.create(U1, title="From bo", body="their text", actor="user", shared_from="bo")
    assert (made.source, made.shared_from, made.last_editor) == ("shared", "bo", "user")
    with pytest.raises(BrainError) as refused:
        await brain.update(U1, made.id, actor="agent", body="agent edit")
    assert refused.value.status == 403
    edited = await brain.update(U1, made.id, body="my edit", agent_editable=True)
    with pytest.raises(BrainError) as refused:
        await brain.update(U1, made.id, actor="agent", body="agent edit")
    assert refused.value.status == 403
    assert edited.edited is True and edited.shared_from == "bo"
    assert (await brain.revert(U1, made.id)).body == "their text"


async def test_only_a_person_imports(brain):
    with pytest.raises(BrainError) as refused:
        await brain.create(U1, title="x", body="y", actor="agent", shared_from="bo")
    assert refused.value.status == 400


async def test_a_shared_skill_starts_proposed_and_a_duplicate_title_is_refused(brain):
    skills = SkillFiles(brain)
    skill, duplicate = await skills.propose(U1, "Restart an app", "hung", "stop, start", "", shared_from="bo")
    assert (skill.status, skill.successes, skill.failures, skill.shared_from, duplicate) == ("proposed", 0, 0, "bo", False)
    assert (await skills.list(U1))[0].shared_from == "bo"
    with pytest.raises(BrainError) as refused:
        await skills.propose(U1, "restart an APP", "hung", "stop, start", "", shared_from="cy")
    assert refused.value.status == 409
    again, duplicate = await skills.propose(U1, "Restart an app", "hung", "stop, start", "")  # an agent proposing the same title
    assert duplicate is True and again.id == skill.id
