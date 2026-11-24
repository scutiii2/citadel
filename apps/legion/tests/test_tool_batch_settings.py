import asyncio
import json
import threading

import pytest

from src.citadel_auth import settings_store
from src.runtime import config_files, run_tools, tool_batch_settings, tuning_overrides
from src.runtime.tool_batch import Call
from tests.test_run_tools import TOOLS, batch_round, step  # noqa: F401
from tests.test_tool_batch import make_round, read_only  # noqa: F401


def test_defaults_apply_until_an_admin_sets_a_value(tmp_path):
    db = tmp_path / "s.db"
    assert tool_batch_settings.current(db) == tool_batch_settings.Settings()
    tuning_overrides.save({"tool_batch.max_parallel": 3, "tool_batch.parallel": False}, db)
    now = tool_batch_settings.current(db)
    assert (now.max_parallel, now.parallel, now.max_steps) == (3, False, 10)
    tuning_overrides.save({"tool_batch.max_parallel": None}, db)  # back to the default
    assert tool_batch_settings.current(db).max_parallel == 8


@pytest.mark.parametrize("path,value", [
    ("tool_batch.max_parallel", 0), ("tool_batch.max_parallel", 17), ("tool_batch.max_steps", 1),
    ("tool_batch.max_steps", True), ("tool_batch.parallel", "yes"), ("tool_batch.max_result_chars", 999),
    ("tool_batch.unknown", 1),
])
def test_a_bad_value_is_refused_and_nothing_is_written(tmp_path, path, value):
    db = tmp_path / "s.db"
    with pytest.raises(tuning_overrides.TuningError):
        tuning_overrides.save({"tool_batch.max_steps": 5, path: value}, db)
    assert tool_batch_settings.overrides(db) == {}


def test_the_tuning_view_lists_the_settings_with_their_defaults_and_overrides(tmp_path):
    raw = tmp_path / "config_tuning.json"
    raw.write_text("{}", encoding="utf-8")
    db = tmp_path / "settings.db"  # the database next to a tuning file
    tuning_overrides.save({"tool_batch.max_steps": 5}, db)
    view = config_files.tuning_view(raw)
    assert view["defaults"]["tool_batch"]["max_steps"] == 10
    assert view["effective"]["tool_batch"]["max_steps"] == 5
    assert view["overrides"]["tool_batch.max_steps"] == 5


def test_a_lower_step_limit_refuses_a_longer_batch(monkeypatch, tmp_path):
    db = tmp_path / "s.db"
    tuning_overrides.save({"tool_batch.max_steps": 2}, db)
    monkeypatch.setattr(tuning_overrides, "PATH", db)
    error = run_tools.validate({"steps": [step("a"), step("b"), step("c")]}, TOOLS)[2]
    assert "1 to 2 steps" in error


def test_parallel_off_runs_read_only_calls_one_at_a_time(monkeypatch, tmp_path):
    db = tmp_path / "s.db"
    tuning_overrides.save({"tool_batch.parallel": False}, db)
    monkeypatch.setattr(tuning_overrides, "PATH", db)
    peak, now, lock = [0], [0], threading.Lock()

    def dispatch(name, arguments, depth):
        with lock:
            now[0] += 1
            peak[0] = max(peak[0], now[0])
        threading.Event().wait(0.05)
        with lock:
            now[0] -= 1
        return name

    runner, _, _ = make_round(dispatch)
    asyncio.run(runner.run([Call("1", "read_a", {}), Call("2", "read_b", {})]))
    assert peak[0] == 1


def test_a_lower_total_cap_cuts_the_reply(monkeypatch, tmp_path):
    db = tmp_path / "s.db"
    tuning_overrides.save({"tool_batch.max_result_chars": 1000}, db)
    monkeypatch.setattr(tuning_overrides, "PATH", db)
    runner, _, _ = batch_round(lambda *a: "x" * 5000)
    outcome = asyncio.run(runner.run([Call("b", run_tools.TOOL_NAME, {"steps": [step("a")]})]))[0]
    row = json.loads(outcome.text)["steps"]["a"]
    assert row["truncated"] and len(row["result"]) == 1000


def test_old_overrides_are_carried_into_the_table_once_and_the_file_is_kept(tmp_path):
    db = tmp_path / "settings.db"
    (tmp_path / "tuning_overrides.json").write_text(json.dumps(
        {"token_limits.default.max_tool_rounds": 20, "token_limits.default.max_output_tokens": 0}), encoding="utf-8")
    settings_store.put(db, "tool_batch", "max_steps", 4)  # the short-lived table of the first version
    settings_store.put(db, "tuning", "token_limits.default.max_tool_rounds", 30)  # an admin's newer value wins
    assert tuning_overrides.load(db) == {"token_limits.default.max_tool_rounds": 30, "tool_batch.max_steps": 4}
    assert (tmp_path / "tuning_overrides.json.migrated").exists() and not (tmp_path / "tuning_overrides.json").exists()
    assert settings_store.read_all(db, "tool_batch") == {}
    assert tuning_overrides.load(db)["tool_batch.max_steps"] == 4  # read again: nothing doubled
