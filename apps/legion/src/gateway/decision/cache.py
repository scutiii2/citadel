"""A small in-memory answer cache. `stream` is not part of the key, so a streamed answer fills the cache for plain calls."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Callable

from src.gateway.decision.contract import DecisionRequest


class AnswerCache:
    def __init__(self, enabled: Callable[[], bool], seconds: Callable[[], int], entries: Callable[[], int]) -> None:
        self._enabled, self._seconds, self._entries = enabled, seconds, entries
        self._rows: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    @staticmethod
    def key(request: DecisionRequest) -> str:
        assets = {name: hashlib.sha256(asset["data_base64"].encode()).hexdigest() for name, asset in request.assets.items()}
        raw = json.dumps([request.gateway, request.text, request.questions, assets, request.min_confidence, request.trace],
                         sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        if not self._enabled():
            return None
        row = self._rows.get(key)
        if row is None or time.monotonic() - row[0] > self._seconds():
            self._rows.pop(key, None)
            return None
        self._rows.move_to_end(key)
        return copy.deepcopy(row[1])

    def put(self, key: str, value: dict[str, Any]) -> None:
        if not self._enabled():
            return
        self._rows[key] = (time.monotonic(), copy.deepcopy(value))
        self._rows.move_to_end(key)
        while len(self._rows) > self._entries():
            self._rows.popitem(last=False)

    def clear(self) -> None:
        """Discard answers when the saved upstream configuration changes."""
        self._rows.clear()
