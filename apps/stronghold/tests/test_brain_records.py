import pytest

from src.brain.records import Record, RecordError, clean_folder, parse, path_id, render, slug

FALLBACK = dict(folder="", fallback_id="f" * 32, fallback_title="stem", fallback_time="2026-01-01T00:00:00")


def sample(**changes):
    base = dict(id="a" * 32, title="Tea notes", body="Likes tea.\n---\nAnd more.\n", folder="drinks", tags=("tea", "daily"),
                source="automatic", last_editor="agent", agent_editable=True, edited=True, revision=4,
                created_at="2026-01-01T00:00:00", updated_at="2026-01-02T00:00:00")
    return Record(**{**base, **changes})


def test_a_record_survives_a_round_trip_with_a_hostile_body():
    record = sample(body='line one\n---\n---\ntitle: "x"\n\n\nlast line with é and 日本\n')
    again = parse(render(record), **{**FALLBACK, "folder": "drinks"})
    assert again == record


def test_an_empty_body_round_trips():
    assert parse(render(sample(body="")), **{**FALLBACK, "folder": "drinks"}).body == ""


def test_a_file_without_a_header_is_adopted_as_a_manual_record():
    record = parse("# Plan\nBuy milk\n", **FALLBACK)
    assert (record.id, record.title, record.body) == ("f" * 32, "stem", "# Plan\nBuy milk\n")
    assert record.source == "manual" and record.last_editor == "user" and record.revision == 1
    assert record.created_at == record.updated_at == "2026-01-01T00:00:00"


def test_windows_line_endings_are_read_as_newlines():
    assert parse(render(sample()).replace("\n", "\r\n"), **{**FALLBACK, "folder": "drinks"}).body == sample().body


@pytest.mark.parametrize("text", [
    '---\nid: "short"\ntitle: "t"\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\ntitle: "t"\nsource: "evil"\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\ntitle: "t"\nrevision: 0\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\ntitle: "t"\ntags: "no"\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\ntitle: not json\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\ntitle: "t"\nedited: "yes"\n---\n\nbody\n',
    '---\nid: "' + "a" * 32 + '"\ntitle: "t"\n\nbody without a closing fence\n',
    '---\n---\nbody\n',
])
def test_a_broken_header_is_refused_not_guessed(text):
    with pytest.raises(RecordError):
        parse(text, **FALLBACK)


def test_unknown_header_keys_are_ignored():
    text = '---\nid: "' + "a" * 32 + '"\ntitle: "t"\nfuture: [1]\n---\n\nbody\n'
    assert parse(text, **FALLBACK).title == "t"


@pytest.mark.parametrize("raw, clean", [("", ""), ("  ", ""), ("work", "work"), ("/work/ideas/", "work/ideas"), ("a-1/b_2", "a-1/b_2")])
def test_folders_are_cleaned(raw, clean):
    assert clean_folder(raw) == clean


@pytest.mark.parametrize("raw", ["..", "a/../b", "./x", "A", "a b", "a\\b", "a//b", "a/b/c/d", "x" * 41, "-a", "a/.hidden", "C:", "a:b", "/etc", "a/NUL", "con"])
def test_unsafe_folders_are_refused(raw):
    with pytest.raises(RecordError):
        clean_folder(raw)


def test_slug_and_path_id():
    assert slug("Hello, Wörld! 2026") == "hello-w-rld-2026"
    assert slug("   ") == "note"
    assert len(slug("x" * 200)) == 40
    assert path_id("a/b.md") == path_id("a/b.md") != path_id("a/c.md")
    assert len(path_id("a/b.md")) == 32
