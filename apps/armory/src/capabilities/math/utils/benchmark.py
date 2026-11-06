"""Repeatable local benchmark: python -m src.capabilities.math.utils.benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
from statistics import median

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.runner import ProcessRunner


class MathBenchmark:
    """Compare identical calculations with cold and reused workers, then reap all."""

    async def _measure(self, requests: int, *, reuse: bool) -> list[dict]:
        runner = ProcessRunner(reuse_workers=reuse, max_requests=32)
        request = SolveRequest(equation="x^2 = -1", data=[])
        try:
            samples = []
            for _ in range(requests):
                result = await runner.run(request)
                if result["status"] != "multiple":
                    raise RuntimeError(f"Benchmark calculation failed: {result['status']}")
                samples.append(result["timings"])
            return samples
        finally:
            await runner.close()

    async def run(self, requests: int = 5) -> dict:
        cold = await self._measure(requests, reuse=False)
        pooled = await self._measure(requests, reuse=True)
        warm = pooled[1:]
        cold_median = median(sample["total_ms"] for sample in cold)
        warm_median = median(sample["total_ms"] for sample in warm)
        return {
            "equation": "x^2 = -1", "requests_per_mode": requests,
            "cold_median_ms": cold_median, "pooled_first_ms": pooled[0]["total_ms"],
            "warm_median_ms": warm_median, "warm_speedup": cold_median / warm_median,
            "warm_median_phases_ms": {name: median(sample.get(name, 0.0) for sample in warm)
                                      for name in ("queue_ms", "startup_ms", "parse_ms", "solve_ms", "verification_ms", "request_ms")},
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare cold and reused Armory mathematics workers")
    parser.add_argument("--requests", type=int, default=5, choices=range(2, 33))
    arguments = parser.parse_args()
    print(json.dumps(await MathBenchmark().run(arguments.requests), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
