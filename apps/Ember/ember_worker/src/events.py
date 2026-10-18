"""What a turn is made of: the request from Ember, and the events a provider reports back."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryLine:
    sender: str
    text: str


@dataclass(frozen=True)
class TurnRequest:
    turn_id: str
    group_id: int
    folder: str
    mode: str  # ask | accept_edits | plan | full_auto
    prompt: str
    history: tuple[HistoryLine, ...] = ()


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    summary: str


@dataclass(frozen=True)
class UsageReport:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Finished:
    """The turn's final answer. A provider yields exactly one Finished or Failed, last."""

    text: str


@dataclass(frozen=True)
class Failed:
    message: str


TurnEvent = TextDelta | ToolCall | UsageReport | Finished | Failed
