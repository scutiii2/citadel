from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.folder_picker import DIALOG_SCRIPT, SubprocessFolderPicker


def pick(script: str, start: str | None = None, timeout: float = 10.0) -> str | None:
    return asyncio.run(SubprocessFolderPicker(script, timeout).pick(start))


def test_the_chosen_folder_is_what_the_dialog_prints() -> None:
    assert pick("print('C:/work/site')") == "C:/work/site"


def test_a_cancelled_dialog_prints_nothing_and_gives_none() -> None:
    assert pick("pass") is None


def test_a_dialog_that_crashes_gives_none() -> None:
    assert pick("raise SystemExit(3)") is None


def test_the_start_folder_is_passed_only_when_it_exists(tmp_path: Path) -> None:
    script = "import sys; print(repr(sys.argv[1]))"

    assert pick(script, str(tmp_path)) == repr(str(tmp_path))
    assert pick(script, str(tmp_path / "missing")) == "''"
    assert pick(script, None) == "''"


def test_a_dialog_nobody_answers_is_stopped() -> None:
    with pytest.raises(asyncio.TimeoutError):
        pick("import time; time.sleep(30)", timeout=0.3)


def test_the_real_dialog_script_is_valid_python() -> None:
    compile(DIALOG_SCRIPT, "dialog", "exec")
