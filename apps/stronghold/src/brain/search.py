"""Keyword search (BM25) over a small set of records. No stemming, no stop words, no vectors.

The index lives in memory and is rebuilt when a record changes; an account has at most a few thousand
files, so a rebuild takes milliseconds.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"[^\W_]{2,}")
K1, B = 1.5, 0.75


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class Bm25Index:
    def __init__(self, documents: dict[str, tuple[str, str, str]]) -> None:
        self._counts: dict[str, Counter[str]] = {}
        self._length: dict[str, int] = {}
        frequency: Counter[str] = Counter()
        for doc_id, (title, body, tags) in documents.items():
            counts: Counter[str] = Counter()
            for word in tokens(title):
                counts[word] += 3
            for word in tokens(tags):
                counts[word] += 2
            for word in tokens(body):
                counts[word] += 1
            self._counts[doc_id] = counts
            self._length[doc_id] = sum(counts.values()) or 1
            frequency.update(counts.keys())
        total = len(documents)
        self._average = (sum(self._length.values()) / total) if total else 1.0
        self._idf = {word: math.log(1 + (total - seen + 0.5) / (seen + 0.5)) for word, seen in frequency.items()}

    def search(self, query: str, limit: int | None) -> list[tuple[str, float]]:
        words = list(dict.fromkeys(tokens(query)))
        if not words:
            return []
        scored: list[tuple[float, str]] = []
        for doc_id, counts in self._counts.items():
            score = 0.0
            for word in words:
                seen = counts.get(word)
                if seen:
                    norm = seen * (K1 + 1) / (seen + K1 * (1 - B + B * self._length[doc_id] / self._average))
                    score += self._idf[word] * norm
            if score > 0:
                scored.append((score, doc_id))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        ranked = [(doc_id, round(score, 4)) for score, doc_id in scored]
        return ranked if limit is None else ranked[:limit]


def make_snippet(body: str, query: str, width: int = 200) -> str:
    """The body on one line; a long one is cut to `width` characters around the first matching word."""
    flat = " ".join(body.split())
    if len(flat) <= width:
        return flat
    lower = flat.lower()
    hits = [at for at in (lower.find(word) for word in dict.fromkeys(tokens(query))) if at >= 0]
    start = max(0, (min(hits) if hits else 0) - width // 4)
    end = min(len(flat), start + width)
    start = max(0, end - width)
    return ("…" if start else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")
