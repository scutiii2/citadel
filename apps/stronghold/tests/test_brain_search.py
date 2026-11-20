from src.brain.search import Bm25Index, make_snippet, tokens


def index(**docs):
    return Bm25Index({name: (title, body, tags) for name, (title, body, tags) in docs.items()})


def test_tokens_are_lowercase_words_of_two_or_more_characters():
    assert tokens("A Café-au-lait, 2 x 42!") == ["café", "au", "lait", "42"]


def test_a_title_match_beats_a_body_match():
    found = index(a=("tea", "x", ""), b=("other", "tea tea", "")).search("tea", None)
    assert [name for name, _ in found] == ["a", "b"]


def test_tags_count_and_unmatched_documents_are_left_out():
    found = index(a=("one", "x", "tea"), b=("two", "y", "")).search("tea", None)
    assert [name for name, _ in found] == ["a"]


def test_a_rare_word_outranks_a_common_one():
    docs = {"a": ("t", "alpha common", ""), "b": ("t", "common", ""), "c": ("t", "common common", "")}
    assert Bm25Index(docs).search("alpha common", None)[0][0] == "a"


def test_limit_and_empty_queries():
    docs = index(a=("x", "tea", ""), b=("y", "tea", ""), c=("z", "tea", ""))
    assert len(docs.search("tea", 2)) == 2
    assert docs.search("", None) == [] and docs.search("!! ?", None) == [] and docs.search("a", None) == []
    assert Bm25Index({}).search("tea", None) == []


def test_scores_are_positive_floats():
    (name, score), = index(a=("x", "tea", "")).search("tea", None)
    assert name == "a" and isinstance(score, float) and score > 0


def test_a_short_body_is_returned_whole_and_a_long_one_is_cut_around_the_hit():
    assert make_snippet("short  body\nhere", "body") == "short body here"
    body = "filler " * 100 + "needle " + "filler " * 100
    snippet = make_snippet(body, "needle", width=60)
    assert "needle" in snippet and len(snippet) <= 62 and snippet.startswith("…") and snippet.endswith("…")
    assert make_snippet("x" * 500, "nothing", width=50).endswith("…")
