"""Bounded aggregate telemetry without equations, values, identifiers, or history."""

from collections import Counter, deque
from math import ceil


class MetricLedger:
    def __init__(self):
        self.calls = 0
        self.statuses = Counter()
        self.queue = deque(maxlen=256)
        self.total = deque(maxlen=256)
        self.reuses = 0
        self.peak = 0
        self.cpu = 0.0

    def record(self, result, queue_ms, total_ms):
        self.calls += 1
        self.statuses[result.get("status", "error")] += 1
        self.queue.append(queue_ms)
        self.total.append(total_ms)
        self.reuses += bool((result.get("execution") or {}).get("worker_reused"))
        resources = result.get("resources") or {}
        self.peak = max(self.peak, resources.get("peak_memory_bytes", 0))
        self.cpu += resources.get("cpu_seconds", 0.0)

    @staticmethod
    def distribution(values):
        ordered = sorted(values)
        return {"p50": ordered[(len(ordered) - 1) // 2], "p95": ordered[ceil(len(ordered) * .95) - 1], "max": ordered[-1]} if ordered else {"p50": 0, "p95": 0, "max": 0}

    def snapshot(self):
        return {"calls": self.calls, "statuses": dict(self.statuses), "worker_reuses": self.reuses,
                "queue_ms": self.distribution(self.queue), "total_ms": self.distribution(self.total),
                "peak_memory_bytes": self.peak, "cpu_seconds": self.cpu, "window_size": len(self.total)}
