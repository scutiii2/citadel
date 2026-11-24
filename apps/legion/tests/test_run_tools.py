import asyncio
import json
import threading

import pytest

from src.runtime import run_tools, tool_batch, tool_batch_settings
from src.runtime.tool_batch import Call
from tests.test_tool_batch import make_round, read_only  # noqa: F401 - the fixture marks read_* as read-only

TOOLS = frozenset({"read_a", "read_b", "read_c", "write_x"})


def step(id, tool="read_a", arguments=None, **more):
    return {"id": id, "tool": tool, "arguments": arguments or {}, **more}


def check(steps, known=()):
    return run_tools.validate({"steps": steps}, TOOLS, known)


def test_validate_builds_waves_and_adds_dependencies_from_refs():
    steps, waves, error = check([step("a"), step("b", "read_b", {"path": {"$ref": "a.items.0"}}), step("c")])
    assert error is None
    assert [[s.id for s in wave] for wave in waves] == [["a", "c"], ["b"]]
    assert steps[1].depends_on == ("a",)


@pytest.mark.parametrize("steps,fragment", [
    ([step("a"), step("a")], "Duplicate step id"),
    ([step("a", "nope")], "not a tool you can run"),
    ([step("a", arguments={"x": {"$ref": "ghost"}})], "unknown step 'ghost'"),
    ([step("a", arguments={"x": {"$ref": "a"}})], "refers to itself"),
    ([step("a", arguments={"x": {"$ref": "b"}}), step("b", arguments={"x": {"$ref": "a"}})], "cycle"),
    ([step("a.b")], "without '.'"),
    ([step("a", "run_tools")], "not a tool you can run"),
])
def test_validate_refuses_a_bad_graph(steps, fragment):
    assert fragment in check(steps)[2]


def test_a_ref_may_name_a_step_of_an_earlier_batch():
    assert check([step("b", arguments={"x": {"$ref": "old"}})], known={"old"})[2] is None


def test_resolve_reads_the_whole_result_or_a_json_field():
    results = {"a": json.dumps({"items": ["x", {"n": 3}]}), "t": "plain"}
    assert run_tools.resolve({"p": {"$ref": "t"}, "q": [{"$ref": "a.items.1.n"}]}, results) == {"p": "plain", "q": [3]}
    with pytest.raises(ValueError, match="not JSON"):
        run_tools.resolve({"$ref": "t.x"}, results)
    with pytest.raises(ValueError, match="no 'items.9'"):
        run_tools.resolve({"$ref": "a.items.9"}, results)


def batch_round(dispatch, **more):
    runner, used, records = make_round(dispatch)
    runner.batch_tools = TOOLS
    return runner, used, records


def run(runner, steps, id="b1"):
    return asyncio.run(runner.run([Call(id, run_tools.TOOL_NAME, {"steps": steps})]))[0]


def test_independent_steps_overlap_and_a_dependent_step_gets_the_reference():
    barrier = threading.Barrier(2, timeout=3)  # both first-wave calls must run together
    seen = []

    def dispatch(name, arguments, depth):
        seen.append((name, arguments))
        if name in ("read_a", "read_b"):
            barrier.wait()
            return json.dumps({"id": name})
        return "joined " + arguments["left"]

    runner, used, records = batch_round(dispatch)
    outcome = run(runner, [step("a"), step("b", "read_b"), step("c", "read_c", {"left": {"$ref": "a.id"}})])
    reply = json.loads(outcome.text)
    assert outcome.ok and outcome.shown == "Ran 3 tools: 3 done"
    assert ("read_c", {"left": "read_a"}) in seen
    assert reply["steps"]["c"]["result"] == "joined read_a"
    assert "result" in reply["steps"]["b"]  # nothing uses b, so it comes back in full
    assert "result" not in reply["steps"]["a"] and reply["steps"]["a"]["result_hidden"].endswith("characters")
    assert runner.results["a"] == json.dumps({"id": "read_a"})
    assert used.count("read_c") == 1 and [r.name for r in records][-1] == "run_tools"


def test_return_true_shows_an_intermediate_result():
    runner, _, _ = batch_round(lambda name, a, d: "text")
    reply = json.loads(run(runner, [{**step("a"), "return": True},
                                    step("b", "read_b", {"x": {"$ref": "a"}})]).text)
    assert reply["steps"]["a"]["result"] == "text"


def test_a_failed_step_skips_what_needs_it_but_not_the_rest():
    def dispatch(name, arguments, depth):
        if name == "read_a":
            raise RuntimeError("boom")
        return "ok"

    runner, _, _ = batch_round(dispatch)
    outcome = run(runner, [step("a"), step("b", "read_b", {"x": {"$ref": "a"}}), step("c", "read_c")])
    reply = json.loads(outcome.text)
    assert not outcome.ok and outcome.shown == "Ran 3 tools: 1 done, 1 failed, 1 skipped"
    assert [reply["steps"][i]["status"] for i in "abc"] == ["failed", "skipped", "done"]
    assert "boom" in reply["steps"]["a"]["result"]
    assert "a" not in runner.results


def test_an_invalid_graph_runs_nothing():
    ran = []
    runner, _, _ = batch_round(lambda *a: ran.append(a) or "x")
    outcome = run(runner, [step("a", "nope")])
    assert not outcome.ok and "not a tool you can run" in outcome.text and ran == []


def test_without_batch_tools_the_call_is_an_ordinary_unknown_tool():
    runner, _, _ = make_round(lambda name, a, d: f"plain {name}")
    outcome = asyncio.run(runner.run([Call("1", "run_tools", {"steps": []})]))[0]
    assert outcome.text == "plain run_tools"


def test_a_big_result_is_cut_and_marked():
    runner, _, _ = batch_round(lambda *a: "x" * (tool_batch_settings.DEFAULTS["max_result_chars"] + 10))
    row = json.loads(run(runner, [step("a")]).text)["steps"]["a"]
    assert row["truncated"] and len(row["result"]) == tool_batch_settings.DEFAULTS["max_result_chars"]
