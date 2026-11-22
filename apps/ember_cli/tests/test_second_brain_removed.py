import dataclasses
import inspect

from src import api


def test_the_summary_has_no_second_brain_fields():
    names = {f.name for f in dataclasses.fields(api.ChatSummary)}
    assert not {"save_to_second_brain", "second_brain_scope"} & names


def test_start_turn_takes_no_second_brain_parameters():
    params = set(inspect.signature(api.EmberClient.start_turn).parameters)
    assert not {"save_to_second_brain", "second_brain_scope"} & params
